"""D3-I: read-only deletion previews. Owner-only, tenant-scoped, aggregate-only, zero writes."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.orm import make_transient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import (
    ApiKey, AuditLog, Dataset, DatasetItem, EvaluationRun, EvaluationSamplingJob, Experiment, ExperimentRun, ExportJob,
    Membership, Organization, OrganizationInvitation, PasswordReset, Project, Prompt, PromptVersion,
    Execution, ExecutionReservation, PredictionSet, Rubric, TaskEvaluation, RubricVersion, Runner, Span, Trace, UsageCounter, User, utcnow,
)
from app.domain.tasks.immutability import PROTECTED
from app.security import create_access_token, generate_api_key, hash_api_key

JAN = datetime(2026, 1, 15, tzinfo=timezone.utc)
FEB = datetime(2026, 2, 15, tzinfo=timezone.utc)
SECRETS = {}


def _h(user_id):
    return {"Authorization": "Bearer " + create_access_token(sub=user_id, email="forged@example.invalid", name=user_id)}


def _project(db, org, pid, owner, traces):
    db.add(Project(id=pid, organization_id=org, name=pid, slug=pid))
    for i, (when, cost) in enumerate(traces):
        tid = f"{pid}-t{i}"
        db.add(Trace(id=tid, project_id=pid, organization_id=org, name="t", environment="prod", status="ok",
                     started_at=when, ended_at=when, duration_ms=1, total_cost_usd=cost, created_at=when,
                     deleted_at=when if i == 0 else None))
        db.add(Span(id=f"{tid}-s", trace_id=tid, type="llm", name="s", status="ok",
                     started_at=when, ended_at=when, duration_ms=1))
    db.add(Rubric(id=f"{pid}-r", project_id=pid, slug="r"))
    db.add(RubricVersion(id=f"{pid}-rv", rubric_id=f"{pid}-r", version=1, yaml_source="", parsed_spec={}, created_by=owner))
    db.add(Prompt(id=f"{pid}-p", project_id=pid, slug="p"))
    db.add(PromptVersion(id=f"{pid}-pv", prompt_id=f"{pid}-p", version=1, template="private template", created_by=owner))
    db.add(Dataset(id=f"{pid}-d", project_id=pid, slug="d"))
    db.add_all(DatasetItem(id=f"{pid}-di{i}", dataset_id=f"{pid}-d", input={"copy": "trace content"}) for i in range(3))
    db.add(Experiment(id=f"{pid}-e", project_id=pid, name="e", dataset_id=f"{pid}-d", rubric_id=f"{pid}-r"))
    db.add(ExperimentRun(id=f"{pid}-er", project_id=pid, experiment_id=f"{pid}-e", status="completed", created_at=FEB,
                         by_variant={"a": {"total_cost_usd": 0.25}, "b": {}}))
    db.add(EvaluationRun(id=f"{pid}-run", project_id=pid, trace_id=f"{pid}-t0", rubric_id=f"{pid}-r", rubric_version=1,
                         triggered_by="test", status="completed", cost_usd=Decimal("0.5"), created_at=JAN))
    db.add(ExportJob(id=f"{pid}-x", project_id=pid, status="completed", file_path=f"/srv/exports/{pid}-secret-path.jsonl",
                     created_by=owner))
    raw, prefix = generate_api_key("prod")
    SECRETS[pid] = (raw, hash_api_key(raw))
    db.add(ApiKey(id=f"{pid}-k", project_id=pid, prefix=prefix, hash=SECRETS[pid][1], name="k", environment="prod"))


@pytest.fixture
def client():
    with SessionLocal() as db:
        for uid in ("owner", "member", "viewer", "co_owner", "other"):
            db.add(User(id=uid, email=f"{uid}@example.com", name=uid, password_hash=f"pw-hash-{uid}"))
        db.add_all([Organization(id="org", name="Org", slug="org"), Organization(id="org2", name="Org2", slug="org2"),
                    Organization(id="org3", name="Org3", slug="org3")])
        db.add_all([Membership(user_id="owner", organization_id="org", role="owner"),
                    Membership(user_id="member", organization_id="org", role="member"),
                    Membership(user_id="viewer", organization_id="org", role="viewer"),
                    Membership(user_id="other", organization_id="org2", role="owner"),
                    Membership(user_id="owner", organization_id="org3", role="owner"),
                    Membership(user_id="co_owner", organization_id="org3", role="owner")])
        db.flush()
        _project(db, "org", "p1", "owner", [(JAN, Decimal("1.25")), (FEB, Decimal("2"))])
        _project(db, "org", "p2", "owner", [(JAN, Decimal("7"))])
        _project(db, "org2", "pb", "other", [(JAN, Decimal("9"))])
        db.flush()
        db.get(Trace, "p1-t1").metadata_json = {"replay_status": "running"}
        # Two unparseable variants in one run must count as one unknown record.
        db.add(ExperimentRun(id="p1-er2", project_id="p1", experiment_id="p1-e", status="running", created_at=FEB,
                             by_variant={"a": {}, "b": {"total_cost_usd": "x"}}))
        for trace, status in (("p1-t0", "started"), ("p1-t1", "uncertain"), ("p2-t0", "completed")):
            db.add(EvaluationSamplingJob(trace_id=trace, project_id=trace[:2], rubric_id=f"{trace[:2]}-r",
                                         rubric_version=1, status=status))
        db.add(OrganizationInvitation(id="i2", organization_id="org", email="sending@example.com", role="viewer",
                                      status="sending", expires_at=utcnow() + timedelta(days=1)))
        db.add(UsageCounter(id="u1", organization_id="org", period="2026-01", cost_usd=Decimal("10"), replay_cost_usd=Decimal("1")))
        db.add(UsageCounter(id="u2", organization_id="org2", period="2026-01", cost_usd=Decimal("99")))
        db.add(AuditLog(id="a1", organization_id="org", actor_user_id="owner", action="x", payload={"ip": "203.0.113.9"}))
        db.add(OrganizationInvitation(id="i1", organization_id="org", email="invitee@example.com", role="member",
                                      invited_by_user_id="owner", status="sent", token_hash="inv-token-hash",
                                      expires_at=utcnow() + timedelta(days=1)))
        db.add(PasswordReset(user_id="owner", request_id="req", credential_version=0, status="sent",
                             token_hash="reset-token-hash", requested_at=utcnow(), created_at=utcnow(),
                             expires_at=utcnow() + timedelta(hours=1)))
        db.commit()
    return TestClient(app)


@pytest.fixture
def no_writes():
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().split(" ", 1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(statement)

    with SessionLocal() as db:
        before = {t.name: db.execute(select(t)).all() for t in Base.metadata.sorted_tables}
    event.listen(engine, "before_cursor_execute", capture)
    yield statements
    event.remove(engine, "before_cursor_execute", capture)
    with SessionLocal() as db:
        assert {t.name: db.execute(select(t)).all() for t in Base.metadata.sorted_tables} == before


def _assert_no_secrets(text):
    forbidden = ["pw-hash-", "inv-token-hash", "reset-token-hash", "secret-path", "/srv/exports", "private template",
                 "trace content", "203.0.113.9", "invitee@example.com", "member@example.com", "co_owner@example.com"]
    forbidden += [part for pair in SECRETS.values() for part in pair]
    leaked = [s for s in forbidden if s in text]
    assert not leaked, leaked


def test_project_preview_counts_only_that_project(client, no_writes):
    r = client.get("/v1/projects/p1/deletion-preview", headers=_h("owner"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"] == "project" and body["target_id"] == "p1" and body["execution_available"] is False
    c = body["resource_counts"]
    assert (c["projects"], c["traces"], c["hidden_traces"], c["spans"], c["dataset_items"], c["rubric_versions"],
            c["prompt_versions"], c["export_jobs"], c["api_keys"]) == (1, 2, 1, 2, 3, 1, 1, 1, 1)
    assert "memberships" not in c and "audit_logs" not in c
    assert body["api_keys"] == {"total": 1, "revoked": 0, "unrevoked": 1, "service_principal_total": 0, "service_principal_revoked": 0}
    assert body["managed_file_references"] == 1
    costs = {(x["source"], x["period"]): (Decimal(x["known_cost_usd"]), x["unknown_cost_records"]) for x in body["known_costs"]}
    assert costs == {
        ("trace_records", "2026-01"): (Decimal("1.25"), 0), ("trace_records", "2026-02"): (Decimal("2"), 0),
        ("evaluation_run_records", "2026-01"): (Decimal("0.5"), 0),
        ("experiment_variant_records", "2026-02"): (Decimal("0.25"), 2),
    }
    deps = {d["code"]: d["count"] for d in body["dependencies"]}
    assert {"execution_contract_not_approved", "rubric_evaluation_references", "dataset_experiment_references",
            "rubric_experiment_references"} <= set(deps)
    assert (deps["evaluation_sampling_jobs_in_flight"], deps["evaluation_sampling_jobs_possible_charge"],
            deps["replay_in_flight"], deps["experiment_runs_in_flight"]) == (1, 1, 1, 1)
    assert "invitations_in_flight" not in deps and "export_jobs_in_flight" not in deps
    assert "organization_finance_and_audit" in body["excluded_scopes"]
    _assert_no_secrets(r.text)
    assert no_writes == []


def test_organization_preview_aggregates_own_projects_and_finance(client, no_writes):
    r = client.get("/v1/organizations/org/deletion-preview", headers=_h("owner"))
    assert r.status_code == 200, r.text
    body = r.json()
    c = body["resource_counts"]
    assert (c["projects"], c["traces"], c["dataset_items"], c["memberships"], c["organization_invitations"],
            c["usage_counters"], c["audit_logs"], c["api_keys"]) == (2, 3, 6, 3, 2, 1, 1, 2)
    usage = {x["source"]: Decimal(x["known_cost_usd"]) for x in body["known_costs"] if x["period"] == "2026-01"
             and x["source"].startswith("organization_")}
    assert usage == {"organization_usage_counter": Decimal("10"), "organization_replay_counter": Decimal("1")}
    deps = {d["code"]: d["count"] for d in body["dependencies"]}
    assert "organization_finance_audit_policy_unresolved" in deps
    assert (deps["invitations_in_flight"], deps["replay_in_flight"]) == (1, 1)  # sent invitation is not in flight
    _assert_no_secrets(r.text)
    assert no_writes == []


def test_organization_preview_counts_only_acceptable_sent_invitations(client):
    past, future = utcnow() - timedelta(minutes=1), utcnow() + timedelta(days=1)
    with SessionLocal() as db:
        db.add_all([
            OrganizationInvitation(id="expired", organization_id="org", email="e@example.com", role="viewer",
                                   status="sent", token_hash="h-expired", expires_at=past),
            OrganizationInvitation(id="revoked", organization_id="org", email="r@example.com", role="viewer",
                                   status="revoked", revoked_at=past, expires_at=future),
            OrganizationInvitation(id="accepted", organization_id="org", email="a@example.com", role="viewer",
                                   status="accepted", accepted_at=past, token_hash="h-accepted", expires_at=future),
            OrganizationInvitation(id="other-org", organization_id="org2", email="o@example.com", role="viewer",
                                   status="sent", token_hash="h-other", expires_at=future),
        ])
        db.commit()
    deps = {d["code"]: d["count"] for d in client.get("/v1/organizations/org/deletion-preview", headers=_h("owner")).json()["dependencies"]}
    assert (deps["invitations_open"], deps["invitations_in_flight"]) == (1, 1)  # only fixture "i1" is open


def test_account_preview_is_self_only_and_reports_last_owner(client, no_writes):
    r = client.get("/v1/auth/me/deletion-preview", headers=_h("owner"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["target_id"] == "owner"
    assert body["memberships"] == [{"organization_id": "org", "role": "owner", "last_owner": True},
                                   {"organization_id": "org3", "role": "owner", "last_owner": False}]
    deps = {(d["code"], d["organization_id"]): d["count"] for d in body["dependencies"]}
    assert deps[("last_owner_transfer_required", "org")] == 1
    assert ("last_owner_transfer_required", "org3") not in deps
    assert deps[("rubric_versions_user_references", None)] == 2
    assert deps[("prompt_versions_user_references", None)] == 2
    c = body["resource_counts"]
    assert (c["password_resets"], c["export_jobs"], c["audit_logs"], c["organization_invitations"]) == (1, 2, 1, 1)
    assert body["known_costs"] == [] and body["api_keys"] == {}
    _assert_no_secrets(r.text)
    # Another user sees only themselves; nothing from org/org3.
    other = client.get("/v1/auth/me/deletion-preview", headers=_h("other")).json()
    assert [mb["organization_id"] for mb in other["memberships"]] == ["org2"]
    assert no_writes == []


@pytest.mark.parametrize("path", ["/v1/projects/p1/deletion-preview", "/v1/organizations/org/deletion-preview"])
@pytest.mark.parametrize("user,status", [("member", 403), ("viewer", 403), ("other", 404), ("co_owner", 404)])
def test_non_owners_and_other_tenants_are_denied(client, no_writes, path, user, status):
    r = client.get(path, headers=_h(user))
    assert (r.status_code, r.json()) == (status, {"detail": "forbidden" if status == 403 else "not_found"})
    assert no_writes == []


@pytest.mark.parametrize("user,status", [("owner", 200), ("member", 404), ("viewer", 404), ("other", 404)])
def test_archived_project_is_not_found_below_owner(client, user, status):
    with SessionLocal() as db:
        db.get(Project, "p2").archived_at = utcnow()
        db.commit()
    r = client.get("/v1/projects/p2/deletion-preview", headers=_h(user))
    assert r.status_code == status, r.text
    if status == 200:
        assert r.json()["resource_counts"]["archived_projects"] == 1
    else:
        assert r.json() == {"detail": "not_found"}


def test_missing_targets_and_cross_tenant_targets_are_indistinguishable(client):
    for path in ("/v1/projects/pb/deletion-preview", "/v1/projects/nope/deletion-preview",
                 "/v1/organizations/org2/deletion-preview", "/v1/organizations/nope/deletion-preview"):
        assert client.get(path, headers=_h("owner")).json() == {"detail": "not_found"}, path


@pytest.mark.parametrize("path", ["/v1/projects/p1/deletion-preview", "/v1/organizations/org/deletion-preview",
                                  "/v1/auth/me/deletion-preview"])
def test_api_keys_and_anonymous_requests_are_rejected(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-EvalOps-Key": SECRETS["p1"][0]}).status_code == 401



@pytest.mark.parametrize("zone", ["America/Fortaleza", "Asia/Tokyo"])
def test_pg_cost_periods_are_utc_regardless_of_session_timezone(zone):
    import os
    from uuid import uuid4

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import NullPool

    from app.domain.services.deletion_preview_service import content_preview

    dedicated = os.getenv("DELETION_PREVIEW_TEST_DATABASE_URL")
    target = dedicated or os.getenv("EVALOPS_OFFLINE_TEST_DATABASE_URL")
    if not target:
        pytest.skip("requires dedicated D3-I PG16")
    url = make_url(target)
    expected = (15637, "evalops_deletion_test") if dedicated else (15636, "offline_test")
    assert (url.get_backend_name(), url.host, url.port, url.database) == (
        "postgresql", "127.0.0.1", *expected), "must target an approved disposable PG16 database"
    schema = "deletion_preview_" + uuid4().hex
    admin = create_engine(target, poolclass=NullPool)
    with admin.begin() as conn:
        assert conn.execute(text("SHOW server_version_num")).scalar().startswith("16")
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    pg = create_engine(target, poolclass=NullPool, connect_args={"options": f"-csearch_path={schema}"})
    late_jan, early_feb = datetime(2026, 1, 31, 23, 30, tzinfo=timezone.utc), datetime(2026, 2, 1, 1, 0, tzinfo=timezone.utc)
    try:
        Base.metadata.create_all(pg)
        with pg.connect() as conn:
            conn.execute(text(f"SET TIME ZONE '{zone}'"))
            db = Session(bind=conn)
            db.add(User(id="u", email="u@example.com", name="u"))
            db.add(Organization(id="org", name="Org", slug="org"))
            db.add(Project(id="p", organization_id="org", name="p", slug="p"))
            db.flush()
            db.add(Rubric(id="r", project_id="p", slug="r"))
            db.add(Dataset(id="d", project_id="p", slug="d"))
            db.flush()
            db.add(Experiment(id="e", project_id="p", name="e", dataset_id="d", rubric_id="r"))
            for i, when in enumerate((late_jan, early_feb)):
                db.add(Trace(id=f"t{i}", project_id="p", organization_id="org", name="t", environment="prod", status="ok",
                             started_at=when, ended_at=when, duration_ms=1, total_cost_usd=Decimal("1"), created_at=when))
            db.flush()
            for i, when in enumerate((late_jan, early_feb)):
                db.add(EvaluationRun(id=f"run{i}", project_id="p", trace_id=f"t{i}", rubric_id="r", rubric_version=1,
                                     triggered_by="test", status="completed", cost_usd=Decimal("1"), created_at=when))
                db.add(ExperimentRun(id=f"er{i}", project_id="p", experiment_id="e", status="completed", created_at=when,
                                     by_variant={"a": {"total_cost_usd": 1}}))
            db.flush()
            costs = content_preview(db, scope="project", target_id="p", organization_id="org").known_costs
            db.rollback()
        assert sorted((c.source, c.period, c.known_cost_usd) for c in costs) == sorted(
            (source, period, Decimal(1)) for source in ("trace_records", "evaluation_run_records", "experiment_variant_records")
            for period in ("2026-01", "2026-02"))
    finally:
        pg.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


TASK_TABLES = ("service_principals", "model_versions", "dataset_snapshots", "snapshot_items", "prediction_sets", "predictions",
               "task_evaluations", "metric_facts", "task_receipts", "experiment_run_evaluations", "investigations",
               "investigation_revisions", "executions", "execution_attempts", "execution_policy_revisions", "runners",
               "runner_credentials", "project_execution_accounts", "execution_plans", "execution_reservations",
               "execution_ledger_entries", "execution_schedules", "execution_leases", "execution_late_reports")
ATTRIBUTION = (("executions", "created_by = 'user'"), ("execution_plans", "created_by = 'user'"),
               ("dataset_snapshots", "created_by = 'user'"),
               ("task_evaluations", "created_by = 'user' AND status NOT IN ('queued','running')"),
               ("execution_policy_revisions", "created_by = 'user'"),
               ("organization_execution_budget_revisions", "created_by = 'user'"), ("investigation_revisions", "author_id = 'user'"),
               ("execution_ledger_entries", "actor_id = 'user'"), ("runners", "owner_user_id = 'user'"))
# Frozen snapshot of FKs without ON DELETE CASCADE; the service derives them from metadata.
NON_CASCADING = {
    "projects": ("execution_policy_revisions", "executions", "investigations", "model_versions", "project_execution_accounts",
                 "runners", "service_principals", "task_receipts", "dataset_snapshots", "execution_plans", "prediction_sets",
                 "task_evaluations"),
    "organizations": ("organization_execution_accounts", "organization_execution_budget_revisions", "execution_ledger_entries",
                      "execution_reservations"),
}


@pytest.fixture
def task_graph():
    """Real HTTP task/execution graph in one project; a sibling project stays empty."""
    import test_execution_budget as eb
    import test_offline_task_api as h
    import test_runner_leases as rl
    from test_runner_control import credential

    from app.domain.tasks import execution_budget as budget

    headers, project, org = h.bootstrap()
    sibling = h.client.post("/v1/projects", headers=headers, json={"organization_id": org, "name": "Sib", "slug": "sib"}).json()["id"]
    eb.configure(headers, project, cost="1", monthly="5", parallel=5)
    sealed = eb.plan(headers, project, cost="1")
    eb.enqueue(headers, project, sealed)  # stays queued with a held reservation
    settled = eb.enqueue(headers, project, sealed)
    sp_headers, _, sp_key = h.key_for(headers, project)
    with SessionLocal() as db:
        prediction_set = db.query(PredictionSet.id).scalar()
        runner = db.query(Runner.id).scalar()
        db.get(Execution, settled["id"]).status = "succeeded"
        reservation = db.get(ExecutionReservation, settled["id"])
        budget.settle(db, reservation, amount=Decimal("0.25"), actor_id="user", measurement_source="fixture", pricing_version="fixture@1")
        reservation.active = False
        db.commit()
    h.post(f"/projects/{project}/task-evaluations", {"prediction_set_id": prediction_set}, headers)
    with SessionLocal() as db:  # a non-terminal evaluation by the same user is not trigger-frozen
        queued = db.query(TaskEvaluation).one()
        db.expunge(queued)
        make_transient(queued)
        queued.id, queued.status, queued.decision = "te-queued", "queued", None
        db.add(queued)
        db.commit()
    h.post(f"/projects/{project}/investigations", {"environment": "dev", "state": {"title": "Investigate", "evidence_refs": []}}, headers)
    runner_key = credential(headers, {"id": runner})
    ctx = {"runner": runner, "key": runner_key["key"]}
    done = rl.leased(ctx)  # leases the queued execution, then completes it
    assert rl.finish(ctx, done, rl.report()).status_code == 200
    assert rl.finish(ctx, done, rl.report(amount="0.5")).status_code == 409  # conflicting report is kept as late report
    eb.enqueue(headers, project, sealed)
    active = rl.claim(ctx, "second").json()["lease"]
    with SessionLocal() as db:
        hashes = [row[0] for row in db.execute(text(
            "SELECT hash FROM api_keys UNION ALL SELECT hash FROM runner_credentials UNION ALL SELECT manifest_hash FROM execution_plans"
            " UNION ALL SELECT token_hash FROM execution_leases UNION ALL SELECT report_hash FROM execution_leases"
            " UNION ALL SELECT content_hash FROM execution_late_reports"))]
    secrets = [sp_headers["X-EvalOps-Key"], sp_key["key"], runner_key["key"], done["lease_token"], active["lease_token"], *hashes]
    return h.client, headers, project, sibling, org, secrets


def test_task_and_execution_models_are_counted_blocked_and_secret_free(task_graph, no_writes):
    client, headers, project, sibling, org, secrets = task_graph
    with SessionLocal() as db:
        total = {t: db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in (*TASK_TABLES, *PROTECTED)}
        immutable = sum(total[t] for t in PROTECTED if t not in ("task_evaluations", "experiment_runs"))
        immutable += db.execute(text("SELECT count(*) FROM task_evaluations WHERE status NOT IN ('queued','running')")).scalar()
        immutable += db.execute(text("SELECT count(*) FROM experiment_runs WHERE kind='task_comparison' AND status IN ('completed','error')")).scalar()
        attributed = sum(db.execute(text(f"SELECT count(*) FROM {t} WHERE {where}")).scalar() for t, where in ATTRIBUTION)
        unconditional = db.execute(text("SELECT count(*) FROM task_evaluations WHERE created_by = 'user'")).scalar()
        references = {target: sum(total.get(t) or db.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in tables)
                      for target, tables in NON_CASCADING.items()}
    assert unconditional == 2 and total["task_evaluations"] == 2
    assert all(total[t] for t in ("executions", "execution_ledger_entries", "runner_credentials", "metric_facts", "investigation_revisions"))
    assert (total["execution_leases"], total["execution_late_reports"]) == (2, 1)

    r = client.get(f"/v1/projects/{project}/deletion-preview", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert {t: body["resource_counts"][t] for t in TASK_TABLES} == {t: total[t] for t in TASK_TABLES}
    c = body["resource_counts"]
    assert (c["active_runners"], c["unrevoked_runner_credentials"], c["active_service_principals"]) == (1, 1, 1)
    assert body["api_keys"]["service_principal_total"] == 1 and body["api_keys"]["service_principal_revoked"] == 0
    deps = {d["code"]: d["count"] for d in body["dependencies"]}
    assert (deps["executions_in_flight"], deps["execution_reservations_held"], deps["task_evaluations_in_flight"]) == (1, 1, 1)
    assert deps["execution_leases_active"] == 1
    assert deps["project_delete_blocked_by_ledger"] == total["execution_ledger_entries"]
    assert deps["non_cascading_project_references"] == references["projects"]
    assert "non_cascading_organization_references" not in deps and "organization_delete_blocked_by_ledger" not in deps
    # The organization budget revision is org-scoped, so only the organization preview counts it.
    project_immutable = immutable - total["organization_execution_budget_revisions"]
    delete_guarded = (total["execution_ledger_entries"] + total["execution_leases"]
                      + total["execution_attempts"] + total["execution_late_reports"])
    assert (deps["immutable_records"], deps["delete_blocked_records"]) == (project_immutable, delete_guarded)
    assert "executions_possible_charge" not in deps and "execution_reservations_unknown" not in deps
    spent = {x["period"]: Decimal(x["known_cost_usd"]) for x in body["known_costs"] if x["source"] == "execution_account_spent"}
    assert list(spent.values()) == [Decimal("0.25") + Decimal("0.12345678")]
    assert not [s for s in secrets if s and s in r.text]

    empty = client.get(f"/v1/projects/{sibling}/deletion-preview", headers=headers).json()
    assert all(empty["resource_counts"][t] == 0 for t in TASK_TABLES)
    assert not {"executions_in_flight", "immutable_records", "delete_blocked_records", "project_delete_blocked_by_ledger",
                "non_cascading_project_references"} & {d["code"] for d in empty["dependencies"]}
    assert not [x for x in empty["known_costs"] if x["source"] == "execution_account_spent"]

    organization = client.get(f"/v1/organizations/{org}/deletion-preview", headers=headers)
    o = organization.json()
    assert (o["resource_counts"]["organization_execution_budget_revisions"], o["resource_counts"]["organization_execution_accounts"]) == (1, 1)
    assert [Decimal(x["known_cost_usd"]) for x in o["known_costs"] if x["source"] == "execution_account_spent"] == [
        Decimal("0.25") + Decimal("0.12345678")]
    o_deps = {d["code"]: d["count"] for d in o["dependencies"]}
    assert o_deps["immutable_records"] == immutable
    assert o_deps["organization_delete_blocked_by_ledger"] == total["execution_ledger_entries"]
    assert (o_deps["non_cascading_project_references"], o_deps["non_cascading_organization_references"]) == (
        references["projects"], references["organizations"])
    assert not [s for s in secrets if s and s in organization.text]

    account = client.get("/v1/auth/me/deletion-preview", headers=headers)
    a_deps = {d["code"]: d["count"] for d in account.json()["dependencies"]}
    assert (a_deps["runners_user_references"], a_deps["service_principals_user_references"]) == (1, 1)
    assert a_deps["immutable_user_attribution"] == attributed
    assert "account_scan_unindexed" in account.json()["limitations"]
    assert not [s for s in secrets if s and s in account.text]
    assert no_writes == []
