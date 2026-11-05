"""Phase 6 — robustez de quota/evaluation/storage.

G-07: monthly quota also covers spans and tokens (not only traces).
G-11: duplicate evaluation returns a clean 409 with existing_run_id.
G-12: judge budget gating uses the org plan.
G-20: usage counter takes a pessimistic lock when running on Postgres.
G-25: DATABASE_URL accepts SQLite (default) and the PG URL is wired in
      docker-compose.prod.yml — Docker not validated locally.
"""
from __future__ import annotations

import os
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.db import Base, SessionLocal, engine, is_postgres, is_sqlite
from app.domain.services import audit_service
from app.domain.services import usage_service
from app.main import app
from app.models import EvaluationRun, Event, ExportJob, Plan, Span, Subscription, Trace, UsageCounter, User
from app.security import create_access_token, new_id

client = TestClient(app)


# ── Helpers ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _auth(user_id: str = "usr_p12", email: str = "p12@example.com") -> dict:
    token = create_access_token(sub=user_id, email=email, name="Phase12")
    return {"Authorization": f"Bearer {token}"}


def _bootstrap() -> tuple[dict, str, str, str]:
    """Create user + org + project. Returns (headers, org_id, project_id, api_key)."""
    with SessionLocal() as db:
        db.add(User(id="usr_p12", email="p12@example.com", name="Phase12"))
        db.commit()
    headers = _auth()
    org = client.post(
        "/v1/organizations", headers=headers, json={"name": "Phase12Org", "slug": "p12-org"}
    ).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={"organization_id": org["id"], "name": "P12", "slug": "p12"},
    ).json()
    key_resp = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()
    return headers, org["id"], project["id"], key_resp["key"]


def _trace_payload(
    client_trace_id: str = "ct_p12_1",
    *,
    spans_count: int = 1,
    tokens_in: int | None = 50,
    tokens_out: int | None = 30,
) -> dict:
    now = datetime.now(timezone.utc)
    spans = []
    for i in range(spans_count):
        spans.append(
            {
                "client_span_id": f"cs_{i}",
                "type": "llm_call",
                "name": "openai.chat",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=100)).isoformat(),
                "status": "ok",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
            }
        )
    return {
        "traces": [
            {
                "client_trace_id": client_trace_id,
                "name": "p12.trace",
                "service": "svc",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(seconds=1)).isoformat(),
                "status": "ok",
                "tags": {},
                "spans": spans,
            }
        ]
    }


def _set_plan_limits(
    org_id: str,
    *,
    monthly_trace_limit: int | None = None,
    monthly_span_limit: int | None = None,
    monthly_token_limit: int | None = None,
    monthly_judge_budget_usd: float | None = None,
) -> None:
    """Mutate the plan attached to ``org_id`` for testing tight quota scenarios."""
    with SessionLocal() as db:
        sub = db.query(Subscription).filter(Subscription.organization_id == org_id).one()
        plan = db.get(Plan, sub.plan_id)
        if monthly_trace_limit is not None:
            plan.monthly_trace_limit = monthly_trace_limit
        if monthly_span_limit is not None:
            plan.monthly_span_limit = monthly_span_limit
        if monthly_token_limit is not None:
            plan.monthly_token_limit = monthly_token_limit
        if monthly_judge_budget_usd is not None:
            plan.monthly_judge_budget_usd = monthly_judge_budget_usd
        db.add(plan)
        db.commit()


def _seed_org_subscription(headers: dict, org_id: str, project_id: str) -> None:
    """Force Subscription + UsageCounter creation up front so plan mutations stick."""
    # /subscription calls ensure_subscription; /usage calls get_or_create_counter.
    client.get(f"/v1/organizations/{org_id}/subscription", headers=headers)
    client.get(f"/v1/organizations/{org_id}/usage", headers=headers)


def _read_counter(org_id: str) -> UsageCounter | None:
    with SessionLocal() as db:
        return (
            db.query(UsageCounter)
            .filter(UsageCounter.organization_id == org_id)
            .one_or_none()
        )


# ── G-07: quota by spans/tokens ──────────────────────────────────────────────

def test_g07_normal_ingest_increments_traces_spans_and_tokens() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    payload = _trace_payload("ct_p12_normal", spans_count=2, tokens_in=10, tokens_out=15)
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 202, resp.text

    counter = _read_counter(org_id)
    assert counter is not None
    assert int(counter.traces_ingested) == 1
    assert int(counter.spans_ingested) == 2
    assert int(counter.tokens_ingested) == (10 + 15) * 2


def test_g07_ingest_exceeding_span_limit_returns_402() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    _set_plan_limits(org_id, monthly_span_limit=1)
    payload = _trace_payload("ct_p12_span_over", spans_count=5, tokens_in=1, tokens_out=1)
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 402
    body = resp.json()["detail"]
    assert body["error"] == "quota_exceeded"
    assert body["field"] == "spans_ingested"


def test_g07_ingest_exceeding_token_limit_returns_402() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    _set_plan_limits(org_id, monthly_token_limit=10)
    payload = _trace_payload("ct_p12_tok_over", spans_count=1, tokens_in=20, tokens_out=20)
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 402
    assert resp.json()["detail"]["field"] == "tokens_ingested"


def test_g07_quota_rejection_does_not_leave_partial_counter_state() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    _set_plan_limits(org_id, monthly_span_limit=2)

    payload = _trace_payload("ct_p12_partial", spans_count=5, tokens_in=1, tokens_out=1)
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 402

    counter = _read_counter(org_id)
    # Only the empty seed counter row (created by the GET /usage call) should exist.
    assert counter is not None
    assert int(counter.traces_ingested) == 0
    assert int(counter.spans_ingested) == 0
    assert int(counter.tokens_ingested) == 0


def test_fix7b4_trace_quota_at_limit_allows_and_increments() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    _set_plan_limits(org_id, monthly_trace_limit=1)

    ok = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=_trace_payload("ct_p12_limit_ok"))
    assert ok.status_code == 202, ok.text

    counter = _read_counter(org_id)
    assert counter is not None
    assert int(counter.traces_ingested) == 1


def test_fix7b4_trace_quota_above_limit_returns_402_without_increment() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    _set_plan_limits(org_id, monthly_trace_limit=1)

    first = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=_trace_payload("ct_p12_limit_1"))
    assert first.status_code == 202, first.text
    second = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=_trace_payload("ct_p12_limit_2"))
    assert second.status_code == 402, second.text
    assert second.json()["detail"]["field"] == "traces_ingested"

    counter = _read_counter(org_id)
    assert counter is not None
    assert int(counter.traces_ingested) == 1


def test_fix7b4_batch_quota_rejection_does_not_persist_trace_graph() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    _set_plan_limits(org_id, monthly_trace_limit=1)

    payload = {
        "traces": [
            _trace_payload("ct_p12_batch_a")["traces"][0],
            _trace_payload("ct_p12_batch_b")["traces"][0],
        ]
    }
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 402, resp.text

    with SessionLocal() as db:
        assert db.query(Trace).filter(Trace.project_id == project_id).count() == 0
        assert db.query(Span).count() == 0
        assert db.query(Event).count() == 0


def test_fix7b4_ingest_usage_failure_rolls_back_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain.services import trace_ingest_service

    headers, _org_id, project_id, api_key = _bootstrap()

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("usage backend unavailable")

    monkeypatch.setattr(trace_ingest_service, "apply_usage_with_quota", _boom)
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=_trace_payload("ct_p12_usage_fail"))

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["ingested"] == 0
    assert len(body["errors"]) == 1
    assert body["errors"][0]["client_trace_id"] == "ct_p12_usage_fail"

    with SessionLocal() as db:
        assert db.query(Trace).filter(Trace.project_id == project_id).count() == 0


# ── G-11: duplicate evaluation → 409 ──────────────────────────────────────────

RUBRIC_LENGTH_YAML = """
slug: dup-rubric
name: Dup Rubric
description: Minimal rubric for dup tests
threshold: 0.0
aggregate: weighted_mean
evaluators:
  - id: len-check
    type: length_bounds
    weight: 1.0
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 0
      max: 10000
"""


def _ingest_simple_trace(api_key: str, client_trace_id: str = "ct_dup") -> str:
    payload = _trace_payload(client_trace_id, spans_count=1, tokens_in=10, tokens_out=10)
    payload["traces"][0]["spans"][0]["messages_out"] = [{"role": "assistant", "content": "ok"}]
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 202, resp.text
    return resp.json()["results"][0]["trace_id"]


def _create_rubric(headers: dict, project_id: str, yaml_source: str) -> str:
    resp = client.post(
        f"/v1/projects/{project_id}/rubrics",
        headers=headers,
        json={"yaml_source": yaml_source},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["rubric"]["id"]


def test_g11_duplicate_evaluation_returns_409_not_500() -> None:
    headers, _, project_id, api_key = _bootstrap()
    trace_id = _ingest_simple_trace(api_key, "ct_dup_a")
    rubric_id = _create_rubric(headers, project_id, RUBRIC_LENGTH_YAML)

    first = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    )
    assert first.status_code == 201

    second = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["error"] == "evaluation_run_duplicate"


def test_g11_duplicate_409_does_not_leak_sql_or_stack() -> None:
    headers, _, project_id, api_key = _bootstrap()
    trace_id = _ingest_simple_trace(api_key, "ct_dup_b")
    rubric_id = _create_rubric(headers, project_id, RUBRIC_LENGTH_YAML)

    client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    )
    resp = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    )
    assert resp.status_code == 409
    body = resp.text.lower()
    for forbidden in ("traceback", "sqlalchemy", "sqlite", "select ", "insert into"):
        assert forbidden not in body, f"leak detected: {forbidden!r}"


def test_g11_duplicate_returns_existing_run_id() -> None:
    headers, _, project_id, api_key = _bootstrap()
    trace_id = _ingest_simple_trace(api_key, "ct_dup_c")
    rubric_id = _create_rubric(headers, project_id, RUBRIC_LENGTH_YAML)

    first = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    ).json()
    expected_run_id = first["run"]["id"]

    second = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["existing_run_id"] == expected_run_id


def test_fix7b4_evaluation_usage_failure_rolls_back_run(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain.services import eval_service

    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    trace_id = _ingest_simple_trace(api_key, "ct_eval_usage_fail")
    rubric_id = _create_rubric(headers, project_id, RUBRIC_LENGTH_YAML)

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("usage cost update failed")

    monkeypatch.setattr(eval_service, "apply_usage_with_quota", _boom)
    with pytest.raises(RuntimeError, match="usage cost update failed"):
        client.post(
            "/v1/evaluations/run",
            headers=headers,
            json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
        )

    with SessionLocal() as db:
        assert db.query(EvaluationRun).filter(EvaluationRun.trace_id == trace_id).count() == 0
        counter = (
            db.query(UsageCounter)
            .filter(UsageCounter.organization_id == org_id, UsageCounter.period == usage_service.current_period())
            .one_or_none()
        )
        assert counter is None or int(counter.evaluations_run or 0) == 0


# ── G-12: judge budget per plan ──────────────────────────────────────────────

JUDGE_RUBRIC_YAML = """
slug: judge-rubric
name: Judge Rubric
description: Uses llm_judge evaluator
threshold: 0.0
aggregate: weighted_mean
evaluators:
  - id: judge
    type: llm_judge
    weight: 1.0
    config:
      prompt: "Rate: {{ trace.output.assistant_message }}"
      model: gpt-4o-mini
"""


def _seed_evaluation_run_cost(org_id: str, project_id: str, cost_usd: float) -> None:
    """Insert a fake EvaluationRun row in the current month with the given cost."""
    with SessionLocal() as db:
        # We need a trace and a rubric to satisfy the FKs, but we already wrote
        # actual ones via the API. Just attach cost to a synthetic run row.
        from app.models import Rubric, Trace
        trace = db.query(Trace).filter(Trace.project_id == project_id).first()
        rubric = db.query(Rubric).filter(Rubric.project_id == project_id).first()
        assert trace is not None and rubric is not None, "seed prerequisites missing"
        # Use a synthetic rubric_version=999 to avoid colliding with real runs
        run = EvaluationRun(
            id=new_id("evr"),
            project_id=project_id,
            trace_id=trace.id,
            rubric_id=rubric.id,
            rubric_version=999,
            triggered_by="seed",
            status="completed",
            cost_usd=cost_usd,
            run_metadata={},
        )
        db.add(run)
        db.commit()


def test_g12_judge_budget_per_plan_blocks_with_402_when_exhausted() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    trace_id = _ingest_simple_trace(api_key, "ct_judge_a")
    rubric_id = _create_rubric(headers, project_id, JUDGE_RUBRIC_YAML)

    _seed_org_subscription(headers, org_id, project_id)
    _set_plan_limits(org_id, monthly_judge_budget_usd=0.001)
    _seed_evaluation_run_cost(org_id, project_id, cost_usd=0.10)

    resp = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    )
    assert resp.status_code == 402
    detail = resp.json()["detail"]
    assert detail["error"] == "judge_budget_exhausted"
    assert detail["budget_usd"] == pytest.approx(0.001, rel=1e-3)


def test_g12_judge_budget_allows_when_within_limit() -> None:
    headers, org_id, project_id, api_key = _bootstrap()
    trace_id = _ingest_simple_trace(api_key, "ct_judge_b")
    rubric_id = _create_rubric(headers, project_id, JUDGE_RUBRIC_YAML)

    _seed_org_subscription(headers, org_id, project_id)
    _set_plan_limits(org_id, monthly_judge_budget_usd=10.0)
    # Spend small fraction
    _seed_evaluation_run_cost(org_id, project_id, cost_usd=0.5)

    resp = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    )
    # llm_judge will fail to call a real LLM, but trigger should not 402.
    assert resp.status_code != 402, resp.text


def test_g12_plan_without_explicit_budget_uses_safe_fallback() -> None:
    """A plan with NULL/zero monthly_judge_budget_usd falls back to 20.0 USD.

    Both ``None`` (legacy column) and ``0`` (explicit zero) collapse to the
    same safe default to avoid silently disabling judges in production.
    """
    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)

    # Case 1: plan column set to 0 — must fall back to 20.0.
    _set_plan_limits(org_id, monthly_judge_budget_usd=0)
    with SessionLocal() as db:
        assert usage_service.judge_budget_for_org(db, org_id) == pytest.approx(20.0)

    # Case 2: an org with no Subscription at all — must fall back to 20.0.
    with SessionLocal() as db:
        assert usage_service.judge_budget_for_org(db, "org_does_not_exist") == pytest.approx(20.0)


# ── G-20: pessimistic lock on usage counter ──────────────────────────────────

def test_fix7b4_usage_counter_create_race_is_recovered(monkeypatch: pytest.MonkeyPatch) -> None:
    period = "2099-02"
    org_id = "org_race_test"
    winner = UsageCounter(
        id="usc_winner",
        organization_id=org_id,
        period=period,
        traces_ingested=0,
        evaluations_run=0,
        exports_created=0,
        cost_usd=0,
        spans_ingested=0,
        tokens_ingested=0,
    )
    calls = {"query": 0}

    class _DummyDB:
        bind = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))

        def begin_nested(self):
            return nullcontext()

        def add(self, _row):  # noqa: ANN001
            return None

        def flush(self):
            raise IntegrityError("INSERT usage_counters", {}, Exception("uq_usage_org_period"))

    class _FakeQuery:
        def one_or_none(self):
            calls["query"] += 1
            return None if calls["query"] == 1 else winner

    monkeypatch.setattr(usage_service, "_counter_query", lambda *args, **kwargs: _FakeQuery())
    row = usage_service.get_or_create_counter(_DummyDB(), org_id, period, lock=True)
    assert row is winner


def test_fix7b4_with_for_update_path_used_when_postgres_lock_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.orm import Query

    headers, org_id, project_id, _ = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)

    calls = {"with_for_update": 0}
    original = Query.with_for_update

    def _tracked_with_for_update(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        calls["with_for_update"] += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(usage_service, "_is_postgres", lambda _db: True)
    monkeypatch.setattr(Query, "with_for_update", _tracked_with_for_update)

    with SessionLocal() as db:
        usage_service.get_or_create_counter(db, org_id, usage_service.current_period(), lock=True)
        usage_service.increment_usage(db, org_id, traces=1)
        db.commit()

    assert calls["with_for_update"] >= 2

def test_g20_pessimistic_lock_used_on_postgres_only() -> None:
    """``increment_usage`` calls ``get_or_create_counter(lock=True)``; that helper
    only emits ``with_for_update`` against Postgres. We assert the dispatch
    here without booting a real Postgres so the test runs in SQLite CI.
    """
    headers, org_id, project_id, _ = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)

    with SessionLocal() as db:
        # Sanity: lock=True must not raise on SQLite (no-op).
        row = usage_service.get_or_create_counter(db, org_id, "2099-01", lock=True)
        assert row is not None
        # And the dispatch helper must reflect the actual dialect.
        assert (db.bind.dialect.name == "postgresql") == usage_service._is_postgres(db)


def test_g20_sqlite_concurrent_increments_are_compatible() -> None:
    """Sequential increments on SQLite must compose deterministically.

    A real concurrent test for SQLite is intentionally omitted: SQLite
    serialises writes via the file-level lock and behaviour under threads is
    timing-dependent. This test pins the documented invariant: repeated
    increments through ``increment_usage`` accumulate without lost updates
    when called from a single process.
    """
    headers, org_id, project_id, _ = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    with SessionLocal() as db:
        for _ in range(7):
            usage_service.increment_usage(db, org_id, traces=1, spans=2, tokens=5)
        db.commit()
    counter = _read_counter(org_id)
    assert int(counter.traces_ingested) == 7
    assert int(counter.spans_ingested) == 14
    assert int(counter.tokens_ingested) == 35


# ── Fix-7B.4: export + audit/usage failure contracts ─────────────────────────

def test_fix7b4_export_usage_failure_marks_job_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.domain.services import export_service

    headers, org_id, project_id, api_key = _bootstrap()
    _seed_org_subscription(headers, org_id, project_id)
    _ingest_simple_trace(api_key, "ct_export_usage_fail")

    def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("usage update failed")

    monkeypatch.setattr(export_service, "apply_usage_with_quota", _boom)
    resp = client.post(
        "/v1/exports",
        headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {}},
    )
    assert resp.status_code == 500
    assert resp.json()["detail"] == "export_failed"

    with SessionLocal() as db:
        job = db.query(ExportJob).filter(ExportJob.project_id == project_id).one()
        assert job.status == "error"
        assert job.completed_at is not None
        counter = (
            db.query(UsageCounter)
            .filter(UsageCounter.organization_id == org_id, UsageCounter.period == usage_service.current_period())
            .one_or_none()
        )
        assert counter is not None
        assert int(counter.exports_created or 0) == 0


def test_fix7b4_export_audit_failure_stays_fire_and_forget(monkeypatch: pytest.MonkeyPatch) -> None:
    headers, _org_id, project_id, api_key = _bootstrap()
    _ingest_simple_trace(api_key, "ct_export_audit_fail")

    class _BrokenAuditLog:
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("audit storage failed")

    monkeypatch.setattr(audit_service, "AuditLog", _BrokenAuditLog)
    create = client.post(
        "/v1/exports",
        headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {}},
    )
    assert create.status_code == 202, create.text

    export_id = create.json()["export_id"]
    job = client.get(f"/v1/exports/{export_id}", headers=headers)
    assert job.status_code == 200, job.text
    assert job.json()["status"] == "completed"


# ── G-25: SQLite default + Postgres prep ─────────────────────────────────────

def test_g25_sqlite_default_when_database_url_unset() -> None:
    """Module-level ``DATABASE_URL`` honours SQLite when no env override."""
    # The current test session inherits whatever DATABASE_URL the runner set;
    # in CI/local without override the engine is SQLite — assert that path.
    if os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL env override active; SQLite default not exercised")
    assert is_sqlite() is True
    assert is_postgres() is False


def test_g25_docker_compose_prod_yaml_is_well_formed() -> None:
    """Validate structure of docker-compose.prod.yml without booting Docker."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_path = repo_root / "docker-compose.prod.yml"
    assert compose_path.exists(), f"missing: {compose_path}"
    text = compose_path.read_text()
    assert "postgres:" in text
    assert "api:" in text
    # Must use sync psycopg driver, not asyncpg.
    assert "postgresql+psycopg" in text
    # Must NOT default a real password.
    assert "POSTGRES_PASSWORD:?" in text or "POSTGRES_PASSWORD:?set" in text


def test_g25_docker_compose_prod_documents_alembic_pending() -> None:
    """The prod compose must explicitly call out that Alembic is Phase 7."""
    repo_root = Path(__file__).resolve().parents[3]
    compose_path = repo_root / "docker-compose.prod.yml"
    text = compose_path.read_text().lower()
    assert "alembic" in text and ("phase 7" in text or "phase7" in text)
