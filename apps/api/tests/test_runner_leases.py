"""Runner lease protocol: no provider calls, no process execution; costs come from fixture reports."""
import copy
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import models as m
from app.db import Base, engine
from app.domain.tasks import runner_leases as leases
import test_offline_task_api as h
from test_execution_budget import configure, enqueue, plan
from test_execution_imports import payload as import_payload
from test_runner_control import create_runner, credential


@pytest.fixture(autouse=True)
def isolated():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def setup(cost="1", monthly="10", parallel=2, admit=None):
    headers, project, org = h.bootstrap()
    configure(headers, project, cost=cost, monthly=monthly, parallel=parallel)
    sealed = plan(headers, project, cost=cost)
    key = credential(headers, {"id": sealed["runner_id"]})
    execution = enqueue(admit or headers, project, sealed)
    return {"headers": headers, "project": project, "org": org, "plan": sealed, "runner": sealed["runner_id"],
            "key": key["key"], "credential": key["id"], "execution": execution["id"]}


def claim(ctx, idem="claim", key=None, runner=None):
    return h.client.post(f"/v1/runners/{runner or ctx['runner']}/leases", headers={"X-EvalOps-Runner-Key": key or ctx["key"], "Idempotency-Key": idem})


def lease_headers(ctx, lease, key=None):
    return {"X-EvalOps-Runner-Key": key or ctx["key"], "X-EvalOps-Lease-Token": lease["lease_token"]}


def beat(ctx, lease, **kwargs):
    return h.client.post(f"/v1/executions/{lease['execution_id']}/attempts/{lease['attempt_id']}/heartbeat", headers=lease_headers(ctx, lease, **kwargs))


def report(status="succeeded", amount="0.12345678"):
    cost = {"state": "provided", "amount_usd": amount, "measurement_source": "fixture_report"} if amount is not None else {"state": "unknown"}
    return {"status": status, "exit_reason": "fixture", "capture_status": "complete", "cost": cost}


def finish(ctx, lease, body, **kwargs):
    return h.client.post(f"/v1/executions/{lease['execution_id']}/attempts/{lease['attempt_id']}/complete", headers=lease_headers(ctx, lease, **kwargs), json=body)


def leased(ctx):
    response = claim(ctx)
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["lease"]


def budget(ctx):
    return h.client.get(f"/v1/executions/{ctx['execution']}/budget", headers=ctx["headers"]).json()


def execution(ctx):
    return h.client.get(f"/v1/executions/{ctx['execution']}", headers=ctx["headers"]).json()


def expire(execution_id):
    with h.SessionLocal() as db:
        db.get(m.ExecutionLease, execution_id).expires_at = m.utcnow() - timedelta(seconds=1)
        db.commit()


def test_single_lease_heartbeat_and_exact_settlement_once():
    ctx = setup()
    lease = leased(ctx)
    assert lease["execution_id"] == ctx["execution"] and lease["lease_ttl_s"] == 60 and lease["heartbeat_interval_s"] == 20
    assert lease["manifest_hash"] == ctx["plan"]["manifest_hash"] and lease["manifest"] == ctx["plan"]["manifest"]
    assert claim(ctx, "other").json() == {"lease": None, "retry_after_s": 5}
    replay = claim(ctx).json()["lease"]
    assert replay["attempt_id"] == lease["attempt_id"] and replay["lease_token"] != lease["lease_token"]
    assert beat(ctx, lease).status_code == 401
    lease = replay
    first = beat(ctx, lease)
    assert first.status_code == 200 and first.json()["cancel_requested"] is False
    assert beat(ctx, lease).status_code == 200
    assert claim(ctx).status_code == 409
    view = execution(ctx)
    assert view["status"] == "running" and view["control"]["lease"]["state"] == "active"
    assert lease["lease_token"] not in str(view)
    with h.SessionLocal() as db:
        assert lease["lease_token"] not in db.get(m.ExecutionLease, ctx["execution"]).token_hash
    done = finish(ctx, lease, report())
    assert done.status_code == 200 and done.json()["status"] == "succeeded"
    assert finish(ctx, lease, report()).json() == done.json()
    conflict = finish(ctx, lease, report(amount="0.5"))
    assert conflict.status_code == 409 and conflict.json()["detail"] == "execution_already_terminal"
    assert beat(ctx, lease).status_code == 409
    balance = budget(ctx)
    assert (balance["known_spent_usd"], balance["held_usd"], balance["slots_active"]) == ("0.12345678", "0.00000000", False)
    assert [entry["kind"] for entry in balance["entries"]] .count("settle") == 1
    view = execution(ctx)
    assert view["status"] == "succeeded" and view["attempts"][0]["id"] == lease["attempt_id"]
    assert view["attempts"][0]["result"]["terminal_source"] == "runner_report"
    with h.SessionLocal() as db:
        account = db.get(m.OrganizationExecutionAccount, (ctx["org"], db.get(m.ExecutionReservation, ctx["execution"]).period))
        assert (account.reserved_units, account.spent_units) == (0, 12345678)
        assert db.query(m.ExecutionLateReport).count() == 1
        for statement in ("UPDATE execution_leases SET state='active'", "UPDATE executions SET status='running'",
                          "UPDATE execution_late_reports SET content='{}'",
                          "DELETE FROM execution_leases", "DELETE FROM execution_late_reports"):
            with pytest.raises(DBAPIError, match="immutable_task_resource"):
                db.execute(text(statement)); db.commit()
            db.rollback()


def test_unknown_cost_keeps_hold_but_frees_slot_after_ack():
    ctx = setup(parallel=1)
    lease = leased(ctx)
    assert finish(ctx, lease, report(status="failed", amount=None)).json()["status"] == "failed"
    balance = budget(ctx)
    assert (balance["state"], balance["known_spent_usd"], balance["held_usd"], balance["slots_active"]) == ("unknown", None, "1.00000000", False)
    enqueue(ctx["headers"], ctx["project"], ctx["plan"])


def test_expired_lease_is_uncertain_keeps_slot_and_refuses_late_publication():
    ctx = setup(parallel=1)
    lease = leased(ctx)
    expire(ctx["execution"])
    late = finish(ctx, lease, report())
    assert late.status_code == 409
    view = execution(ctx)
    assert view["status"] == "uncertain" and view["control"]["lease"]["state"] == "expired"
    assert view["attempts"][0]["result"]["exit_reason"] == "lease_expired"
    balance = budget(ctx)
    assert (balance["state"], balance["known_spent_usd"], balance["held_usd"], balance["slots_active"]) == ("unknown", None, "1.00000000", True)
    assert claim(ctx, "again").json() == {"lease": None, "retry_after_s": 5}  # uncertainty never re-dispatches
    enqueue(ctx["headers"], ctx["project"], ctx["plan"], expected=429)
    with h.SessionLocal() as db:
        assert db.query(m.ExecutionLateReport).one().reason == "lease_closed"
        assert db.query(m.ExecutionLedgerEntry).filter_by(kind="settle").count() == 0
    assert h.client.post(f"/v1/executions/{ctx['execution']}/cancel", headers=ctx["headers"]).json()["status"] == "uncertain"


def test_expiry_is_noticed_by_cancel_without_runner_traffic():
    ctx = setup()
    leased(ctx)
    expire(ctx["execution"])
    assert h.client.post(f"/v1/executions/{ctx['execution']}/cancel", headers=ctx["headers"]).json()["status"] == "uncertain"


def test_expiry_is_noticed_by_empty_queue_claim_and_truly_idle_poll_takes_no_write_locks():
    from sqlalchemy import event
    ctx = setup()
    leased(ctx)
    expire(ctx["execution"])
    swept = claim(ctx, "sweep-expired")
    assert swept.status_code == 200 and swept.json() == {"lease": None, "retry_after_s": 5}
    view = execution(ctx)
    assert view["status"] == "uncertain" and view["control"]["lease"]["state"] == "expired"
    writes = []
    def record_writes(conn, cursor, statement, parameters, context, executemany):
        upper = statement.lstrip().upper()
        if upper.startswith(("UPDATE", "INSERT", "DELETE")) or "FOR UPDATE" in upper:
            writes.append(statement)
    event.listen(engine, "before_cursor_execute", record_writes)
    try:
        idle_poll = claim(ctx, "truly-idle")
    finally:
        event.remove(engine, "before_cursor_execute", record_writes)
    assert idle_poll.status_code == 200 and idle_poll.json() == {"lease": None, "retry_after_s": 5}
    assert writes == []


def test_cancel_needs_runner_ack_and_unrequested_cancel_is_rejected():
    ctx = setup()
    lease = leased(ctx)
    assert finish(ctx, lease, report(status="cancelled")).status_code == 422
    requested = h.client.post(f"/v1/executions/{ctx['execution']}/cancel", headers=ctx["headers"]).json()
    assert requested["status"] == "running" and requested["cancel_requested_at"]
    assert beat(ctx, lease).json()["cancel_requested"] is True
    assert finish(ctx, lease, report(status="cancelled", amount="0.01")).json()["status"] == "cancelled"
    assert budget(ctx)["known_spent_usd"] == "0.01000000"
    assert execution(ctx)["attempts"][0]["result"]["cancel_requested"] is True


def test_completion_before_cancel_ack_is_kept_and_cancel_after_terminal_is_noop():
    ctx = setup()
    lease = leased(ctx)
    h.client.post(f"/v1/executions/{ctx['execution']}/cancel", headers=ctx["headers"]).raise_for_status()
    assert finish(ctx, lease, report()).json()["status"] == "succeeded"
    assert h.client.post(f"/v1/executions/{ctx['execution']}/cancel", headers=ctx["headers"]).json()["status"] == "succeeded"


@pytest.mark.parametrize("action", ["disable", "revoke"])
def test_disabled_runner_or_revoked_credential_loses_lease(action):
    ctx = setup()
    lease = leased(ctx)
    if action == "disable":
        h.post(f"/runners/{ctx['runner']}/disable", {}, ctx["headers"], expected=200)
    else:
        h.client.post(f"/v1/runners/{ctx['runner']}/credentials/{ctx['credential']}/revoke", headers=ctx["headers"]).raise_for_status()
    assert claim(ctx).status_code == 401
    assert beat(ctx, lease).status_code == 401
    assert finish(ctx, lease, report()).status_code == 401
    view = execution(ctx)
    assert view["status"] == "uncertain" and view["control"]["lease"]["state"] == "lost"
    assert budget(ctx)["state"] == "unknown"


def test_restricted_source_cancels_unstarted_and_makes_running_uncertain():
    headers, project, _ = h.bootstrap()
    configure(headers, project, monthly="10")
    access = {"environment": "dev", "independent": True, "allowed_environments": ["dev", "prod"],
              "justification": "Independent synthetic fixture", "evidence": "Synthetic construction v1"}
    dataset = h.post(f"/projects/{project}/datasets", {"slug": "shared", "task_type": "regression", "task_schema": {"target": {"name": "price", "unit": "BRL"}},
        "access": access, "items": [{"sample_id": "s1", "input": {}, "expected_output": {"value": 1}}]}, headers)
    snap = h.post(f"/datasets/{dataset['id']}/snapshots", {"environment": "dev", "allowed_environments": ["dev", "prod"]}, headers)
    model = h.post(f"/projects/{project}/model-versions", {"model": {"name": "shared", "version_ref": "v1"}, "access": access}, headers)
    runner = create_runner(headers, project)
    sealed = h.post(f"/projects/{project}/execution-plans", {"runner_id": runner["id"], "manifest": import_payload(snap, model)["manifest"]}, headers)
    ctx = {"headers": headers, "runner": runner["id"], "key": credential(headers, runner)["key"], "execution": enqueue(headers, project, sealed)["id"]}
    queued = enqueue(headers, project, sealed)
    lease = leased(ctx)
    h.post(f"/task-resources/dataset/{dataset['id']}/restrict", {"allowed_environments": ["prod"], "access_revision": 1}, headers, expected=200)
    assert beat(ctx, lease).status_code == 409
    assert claim(ctx, "next").json() == {"lease": None, "retry_after_s": 5}
    with h.SessionLocal() as db:
        assert db.get(m.Execution, ctx["execution"]).status == "uncertain"
        assert db.get(m.Execution, queued["id"]).status == "cancelled"
        reservation = db.get(m.ExecutionReservation, queued["id"])
        assert (reservation.state, reservation.spent_units, reservation.active) == ("settled", 0, False)


def test_policy_disabled_after_admission_cancels_before_lease():
    ctx = setup()
    response = h.client.put(f"/v1/projects/{ctx['project']}/execution-policy", headers={**ctx["headers"], "If-Match": "1", "Idempotency-Key": "off"}, json={"enabled": False})
    assert response.status_code == 200
    assert claim(ctx).json() == {"lease": None, "retry_after_s": 5}
    assert execution(ctx)["status"] == "cancelled" and budget(ctx)["held_usd"] == "0.00000000"


@pytest.mark.parametrize("loss", ["key_revoked", "scope_lost", "source_restricted", "policy_disabled", "budget_disabled", "reservation_lost"])
def test_claim_replay_refused_after_authorization_loss(loss):
    headers, project, _ = h.bootstrap()
    configure(headers, project, monthly="10", parallel=1)
    access = {"environment": "dev", "independent": True, "allowed_environments": ["dev", "prod"],
              "justification": "Independent synthetic fixture", "evidence": "Synthetic construction v1"}
    dataset = h.post(f"/projects/{project}/datasets", {"slug": "shared", "task_type": "regression", "task_schema": {"target": {"name": "price", "unit": "BRL"}},
        "access": access, "items": [{"sample_id": "s1", "input": {}, "expected_output": {"value": 1}}]}, headers)
    snap = h.post(f"/datasets/{dataset['id']}/snapshots", {"environment": "dev", "allowed_environments": ["dev", "prod"]}, headers)
    model = h.post(f"/projects/{project}/model-versions", {"model": {"name": "shared", "version_ref": "v1"}, "access": access}, headers)
    runner = create_runner(headers, project)
    sealed = h.post(f"/projects/{project}/execution-plans", {"runner_id": runner["id"], "manifest": import_payload(snap, model)["manifest"]}, headers)
    key, _, raw = h.key_for(headers, project)
    ctx = {"headers": headers, "project": project, "runner": runner["id"], "key": credential(headers, runner)["key"],
           "execution": enqueue(key, project, sealed)["id"]}
    first = leased(ctx)
    if loss == "key_revoked":
        h.client.post(f"/v1/projects/{project}/api-keys/{raw['id']}/revoke", headers=headers).raise_for_status()
    elif loss == "scope_lost":
        with h.SessionLocal() as db:
            db.get(m.ApiKey, raw["id"]).scopes = "read,write"
            db.commit()
    elif loss == "source_restricted":
        h.post(f"/task-resources/dataset/{dataset['id']}/restrict", {"allowed_environments": ["prod"], "access_revision": 1}, headers, expected=200)
    elif loss == "policy_disabled":
        h.client.put(f"/v1/projects/{project}/execution-policy", headers={**headers, "If-Match": "1", "Idempotency-Key": "off"}, json={"enabled": False}).raise_for_status()
    elif loss == "budget_disabled":
        h.client.put(f"/v1/projects/{project}/organization-execution-budget", headers={**headers, "If-Match": "1"},
                     json={"enabled": False, "monthly_budget_usd": "10", "max_parallel": 1}).raise_for_status()
    elif loss == "reservation_lost":
        with h.SessionLocal() as db:
            db.get(m.ExecutionReservation, ctx["execution"]).active = False
            db.commit()
    refused = claim(ctx)
    assert refused.status_code == 409
    with h.SessionLocal() as db:
        assert db.get(m.Execution, ctx["execution"]).status == "uncertain"
        assert db.get(m.ExecutionLease, ctx["execution"]).state == "lost"
    assert beat(ctx, first).status_code == 409
    assert claim(ctx).status_code == 409


@pytest.mark.parametrize("amount", ["0.12345678", None])
def test_original_key_revoked_mid_run_refuses_publication_and_handles_spend(amount):
    headers, project, _ = h.bootstrap()
    key, _, raw = h.key_for(headers, project)
    configure(headers, project, monthly="10", parallel=1)
    sealed = plan(headers, project)
    ctx = {"headers": headers, "project": project, "plan": sealed, "runner": sealed["runner_id"],
           "key": credential(headers, {"id": sealed["runner_id"]})["key"], "execution": enqueue(key, project, sealed)["id"]}
    lease = leased(ctx)
    assert beat(ctx, lease).status_code == 200
    h.client.post(f"/v1/projects/{project}/api-keys/{raw['id']}/revoke", headers=headers).raise_for_status()
    assert finish(ctx, lease, report(amount=amount)).status_code == 409
    assert finish(ctx, lease, report(amount=amount)).status_code == 409
    view = execution(ctx)
    assert view["status"] == "uncertain"
    balance = budget(ctx)
    if amount is not None:
        assert (balance["state"], balance["known_spent_usd"], balance["held_usd"], balance["slots_active"]) == ("settled", amount, "0.00000000", False)
        assert [entry["kind"] for entry in balance["entries"]].count("settle") == 1
        assert view["attempts"][0]["result"]["cost"]["state"] == "provided"
        assert view["attempts"][0]["result"]["cost"]["amount_usd"] == amount
        assert finish(ctx, lease, report(amount="0.50000000")).status_code == 409
        assert [entry["kind"] for entry in budget(ctx)["entries"]].count("settle") == 1
        enqueue(headers, project, sealed)
    else:
        assert (balance["state"], balance["known_spent_usd"], balance["held_usd"], balance["slots_active"]) == ("unknown", None, "1.00000000", True)
        assert [entry["kind"] for entry in balance["entries"]].count("settle") == 0
        assert view["attempts"][0]["result"]["cost"]["state"] == "unknown"
        enqueue(headers, project, sealed, expected=429)
    with h.SessionLocal() as db:
        assert db.query(m.ExecutionLateReport).filter_by(reason="revalidation_failed").count() == 1


def test_runner_identity_is_bound_to_runner_credential_and_lease():
    ctx = setup()
    other = h.post(f"/projects/{ctx['project']}/execution-plans", {"runner_id": create_runner(ctx["headers"], ctx["project"])["id"], "manifest": ctx["plan"]["manifest"]}, ctx["headers"])
    other_key = credential(ctx["headers"], {"id": other["runner_id"]})["key"]
    assert claim(ctx, key=other_key, runner=other["runner_id"]).json() == {"lease": None, "retry_after_s": 5}
    assert claim(ctx, key=other_key).status_code == 401
    assert h.client.post(f"/v1/runners/{ctx['runner']}/leases", headers={"X-EvalOps-Key": ctx["key"], "Idempotency-Key": "k"}).status_code == 401
    assert h.client.post(f"/v1/runners/{ctx['runner']}/leases", headers={**ctx["headers"], "Idempotency-Key": "k"}).status_code == 401
    assert claim(ctx, idem="").status_code == 422
    lease = leased(ctx)
    assert beat(ctx, lease, key=other_key).status_code == 401
    second_key = credential(ctx["headers"], {"id": ctx["runner"]})["key"]
    assert beat(ctx, lease, key=second_key).status_code == 401  # lease is bound to the claiming credential
    forged = {**lease, "lease_token": "forged"}
    assert beat(ctx, forged).status_code == 401
    assert beat(ctx, {**lease, "attempt_id": "attempt_other"}).status_code == 401
    assert h.client.post(f"/v1/executions/{lease['execution_id']}/attempts/{lease['attempt_id']}/heartbeat", headers=ctx["headers"]).status_code == 401
    assert beat(ctx, lease).status_code == 200


def test_heartbeat_renews_ttl_and_respects_wall_time_limit(monkeypatch):
    ctx = setup()
    lease = leased(ctx)
    with h.SessionLocal() as db:
        db.get(m.ExecutionLease, ctx["execution"]).expires_at = m.utcnow() + timedelta(seconds=1)
        db.commit()
    renewed = datetime.fromisoformat(beat(ctx, lease).json()["expires_at"])
    assert renewed >= m.utcnow() + timedelta(seconds=55)
    assert finish(ctx, lease, report()).status_code == 200

    headers, project = ctx["headers"], ctx["project"]
    runner = {"id": ctx["runner"]}
    key = ctx["key"]
    short_manifest = copy.deepcopy(ctx["plan"]["manifest"])
    short_manifest["limits"]["wall_time_s"] = 25
    short_plan = h.post(f"/projects/{project}/execution-plans", {"runner_id": runner["id"], "manifest": short_manifest}, headers)
    short_ctx = {"headers": headers, "project": project, "runner": runner["id"], "key": key,
                 "execution": enqueue(headers, project, short_plan)["id"]}
    now = m.utcnow()
    monkeypatch.setattr(m, "utcnow", lambda: now)
    short_lease = claim(short_ctx, "claim-short").json()["lease"]
    assert short_lease["lease_ttl_s"] == 25 + leases.WALL_TIME_GRACE_S
    assert datetime.fromisoformat(short_lease["expires_at"]) == now + timedelta(seconds=25 + leases.WALL_TIME_GRACE_S)
    assert finish(short_ctx, short_lease, report()).status_code == 200

    bounded_manifest = copy.deepcopy(ctx["plan"]["manifest"])
    bounded_manifest["limits"]["wall_time_s"] = 70
    bounded_plan = h.post(f"/projects/{project}/execution-plans", {"runner_id": runner["id"], "manifest": bounded_manifest}, headers)
    bounded_ctx = {"headers": headers, "project": project, "runner": runner["id"], "key": key,
                   "execution": enqueue(headers, project, bounded_plan)["id"]}
    start = now + timedelta(seconds=100)
    monkeypatch.setattr(m, "utcnow", lambda: start)
    bounded_lease = claim(bounded_ctx, "claim-bounded").json()["lease"]
    assert datetime.fromisoformat(bounded_lease["expires_at"]) == start + timedelta(seconds=60)
    near_limit = start + timedelta(seconds=55)
    monkeypatch.setattr(m, "utcnow", lambda: near_limit)
    near_beat = beat(bounded_ctx, bounded_lease)
    assert near_beat.status_code == 200
    assert datetime.fromisoformat(near_beat.json()["expires_at"]) == start + timedelta(seconds=70 + leases.WALL_TIME_GRACE_S)
    with h.SessionLocal() as db:
        db.get(m.ExecutionLease, bounded_ctx["execution"]).expires_at = start + timedelta(seconds=150)
        db.commit()
    after_limit = start + timedelta(seconds=70 + leases.WALL_TIME_GRACE_S)
    monkeypatch.setattr(m, "utcnow", lambda: after_limit)
    assert beat(bounded_ctx, bounded_lease).status_code == 409
    view = execution(bounded_ctx)
    assert view["status"] == "uncertain" and view["control"]["lease"]["state"] == "expired"


@pytest.mark.parametrize("cost,reported", [("999999999.99999999", "999999999.99999999"), ("0.01000000", "0.02000000")])
def test_reported_cost_settles_exactly_and_overspend_is_preserved(cost, reported):
    ctx = setup(cost=cost, monthly="1000000000", parallel=1)
    lease = leased(ctx)
    assert finish(ctx, lease, report(amount=reported)).status_code == 200
    balance = budget(ctx)
    assert balance["known_spent_usd"] == reported and balance["held_usd"] == "0.00000000"
    assert {entry["kind"]: entry["amount_usd"] for entry in balance["entries"]} == {"reserve": cost, "settle": reported, "release": cost}
    warnings = execution(ctx)["attempts"][0]["result"]["warnings"]
    assert warnings == ([] if cost == reported else ["reported_cost_exceeds_reserved_limit"])


@pytest.mark.parametrize("finish_after_s,accepted", [(62, True), (60 + leases.WALL_TIME_GRACE_S + 1, False)])
def test_timed_out_report_inside_wall_time_grace_settles(monkeypatch, finish_after_s, accepted):
    ctx = setup()  # manifest wall_time_s=60
    start = m.utcnow()
    monkeypatch.setattr(m, "utcnow", lambda: start)
    lease = leased(ctx)
    monkeypatch.setattr(m, "utcnow", lambda: start + timedelta(seconds=50))
    assert beat(ctx, lease).status_code == 200
    monkeypatch.setattr(m, "utcnow", lambda: start + timedelta(seconds=finish_after_s))
    response = finish(ctx, lease, report(status="timed_out", amount="0.25"))
    balance = budget(ctx)
    if accepted:
        assert response.status_code == 200 and response.json()["status"] == "timed_out"
        assert (balance["state"], balance["known_spent_usd"], balance["slots_active"]) == ("settled", "0.25000000", False)
    else:
        assert response.status_code == 409 and execution(ctx)["status"] == "uncertain"
        assert (balance["state"], balance["known_spent_usd"], balance["slots_active"]) == ("unknown", None, True)
