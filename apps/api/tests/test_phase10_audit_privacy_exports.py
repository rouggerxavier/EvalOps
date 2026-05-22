"""Phase 4 tests: G-06 audit log, G-08 redaction, G-09/G-10 exports, G-21 soft delete."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import AuditLog, Event, ExportJob, Span, Trace, User
from app.security import create_access_token


# ── Helpers ───────────────────────────────────────────────────────────────────

def _client() -> TestClient:
    return TestClient(app)


def _auth_header(user_id: str = "usr_p10", email: str = "p10@example.com") -> dict[str, str]:
    token = create_access_token(sub=user_id, email=email, name="Phase10")
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> tuple[str, str, str, dict]:
    """Return (org_id, project_id, api_key, auth_headers)."""
    with SessionLocal() as db:
        db.add(User(id="usr_p10", email="p10@example.com", name="Phase10"))
        db.commit()
    headers = _auth_header()
    org = client.post(
        "/v1/organizations", headers=headers,
        json={"name": "AuditOrg", "slug": "audit-org"},
    ).json()
    project = client.post(
        "/v1/projects", headers=headers,
        json={"organization_id": org["id"], "name": "AuditProj", "slug": "audit-proj"},
    ).json()
    key_resp = client.post(
        f"/v1/projects/{project['id']}/api-keys", headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()
    return org["id"], project["id"], key_resp["key"], headers


def _ts() -> tuple[str, str]:
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(seconds=1)
    return t0.isoformat(), t1.isoformat()


def _ingest(client: TestClient, api_key: str, client_trace_id: str, tags: dict | None = None,
            spans: list | None = None, extra_headers: dict | None = None) -> dict:
    t0, t1 = _ts()
    if spans is None:
        spans = [{
            "client_span_id": "sp1",
            "type": "llm_call",
            "name": "test-span",
            "started_at": t0,
            "ended_at": t1,
            "status": "ok",
            "messages_in": [{"role": "user", "content": "hello"}],
            "messages_out": [{"role": "assistant", "content": "world"}],
            "input": {"text": "hello"},
            "output": {"text": "world"},
        }]
    payload = {
        "traces": [{
            "client_trace_id": client_trace_id,
            "name": "test.trace",
            "environment": "prod",
            "started_at": t0,
            "ended_at": t1,
            "status": "ok",
            "tags": tags or {},
            "spans": spans,
        }]
    }
    headers = {"X-EvalOps-Key": api_key}
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/v1/traces", headers=headers, json=payload).json()


def _audit_logs(action: str | None = None) -> list[dict]:
    with SessionLocal() as db:
        q = db.query(AuditLog)
        if action:
            q = q.filter(AuditLog.action == action)
        return [
            {"action": a.action, "target_type": a.target_type, "target_id": a.target_id, "payload": a.payload}
            for a in q.all()
        ]


RUBRIC_YAML = """
slug: audit-rubric
name: Audit Test Rubric
description: Rubric for Phase 4 audit tests
threshold: 0.5
evaluators:
  - id: len-check
    type: length_bounds
    config: {}
"""


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ── G-06: Audit log ───────────────────────────────────────────────────────────

def test_create_api_key_generates_audit() -> None:
    client = _client()
    _, project_id, _, headers = _bootstrap(client)
    # bootstrap already creates one key; create a second
    res = client.post(
        f"/v1/projects/{project_id}/api-keys", headers=headers,
        json={"name": "extra-key", "environment": "dev", "scopes": ["ingest"]},
    )
    assert res.status_code == 201, res.text
    logs = _audit_logs("api_key.created")
    assert len(logs) >= 1
    assert logs[-1]["target_type"] == "api_key"
    assert logs[-1]["payload"]["project_id"] == project_id


def test_revoke_api_key_generates_audit() -> None:
    client = _client()
    _, project_id, _, headers = _bootstrap(client)
    key_resp = client.post(
        f"/v1/projects/{project_id}/api-keys", headers=headers,
        json={"name": "to-revoke", "environment": "dev", "scopes": ["ingest"]},
    ).json()
    key_id = key_resp["id"]
    res = client.post(f"/v1/projects/{project_id}/api-keys/{key_id}/revoke", headers=headers)
    assert res.status_code == 204, res.text
    logs = _audit_logs("api_key.revoked")
    assert len(logs) >= 1
    assert logs[-1]["target_id"] == key_id


def test_create_rubric_generates_audit() -> None:
    client = _client()
    _, project_id, _, headers = _bootstrap(client)
    res = client.post(
        f"/v1/projects/{project_id}/rubrics", headers=headers,
        json={"yaml_source": RUBRIC_YAML},
    )
    assert res.status_code == 201, res.text
    rubric_id = res.json()["rubric"]["id"]
    assert len(_audit_logs("rubric.created")) >= 1
    assert _audit_logs("rubric.created")[-1]["target_id"] == rubric_id
    assert len(_audit_logs("rubric_version.created")) >= 1


def test_run_evaluation_generates_audit() -> None:
    client = _client()
    _, project_id, api_key, headers = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-eval")
    trace_id = ingest["results"][0]["trace_id"]
    rubric_id = client.post(
        f"/v1/projects/{project_id}/rubrics", headers=headers,
        json={"yaml_source": RUBRIC_YAML},
    ).json()["rubric"]["id"]
    res = client.post(
        "/v1/evaluations/run", headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
    )
    assert res.status_code == 201, res.text
    run_id = res.json()["run"]["id"]
    logs = _audit_logs("evaluation.run")
    assert len(logs) >= 1
    assert logs[-1]["target_id"] == run_id
    assert logs[-1]["payload"]["trace_id"] == trace_id


def test_run_experiment_generates_audit() -> None:
    client = _client()
    _, project_id, _, headers = _bootstrap(client)
    ds_id = client.post(
        f"/v1/projects/{project_id}/datasets", headers=headers,
        json={"slug": "audit-ds", "description": "test", "source": "manual"},
    ).json()["id"]
    client.post(
        f"/v1/datasets/{ds_id}/items", headers=headers,
        json={"items": [{"input": {"text": "hello"}, "expected_output": {"text": "hello"}}]},
    )
    rubric_id = client.post(
        f"/v1/projects/{project_id}/rubrics", headers=headers,
        json={"yaml_source": RUBRIC_YAML},
    ).json()["rubric"]["id"]
    exp_res = client.post(
        f"/v1/projects/{project_id}/experiments", headers=headers,
        json={
            "name": "Audit Exp",
            "dataset_id": ds_id,
            "rubric_id": rubric_id,
            "variants": [{"name": "variant-a", "params": {}}],
            "pass_criteria": {},
        },
    )
    assert exp_res.status_code == 201, exp_res.text
    exp_id = exp_res.json()["id"]
    res = client.post(f"/v1/experiments/{exp_id}/run", headers=headers, json={"triggered_by": "test"})
    assert res.status_code == 202, res.text
    logs = _audit_logs("experiment.run")
    assert len(logs) >= 1
    assert logs[-1]["payload"]["experiment_id"] == exp_id


def test_delete_trace_generates_audit() -> None:
    client = _client()
    _, project_id, api_key, headers = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-del-audit")
    trace_id = ingest["results"][0]["trace_id"]
    res = client.delete(f"/v1/traces/{trace_id}", headers=headers)
    assert res.status_code == 204, res.text
    logs = _audit_logs("trace.deleted")
    assert len(logs) >= 1
    assert logs[-1]["target_id"] == trace_id
    assert logs[-1]["target_type"] == "trace"


# ── G-08: Redaction ───────────────────────────────────────────────────────────

def test_ingest_without_redaction_preserves_messages() -> None:
    client = _client()
    _, _proj, api_key, _ = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-normal")
    trace_id = ingest["results"][0]["trace_id"]
    with SessionLocal() as db:
        t = db.get(Trace, trace_id)
        assert not t.redacted
        spans = db.query(Span).filter(Span.trace_id == trace_id).all()
        assert any(sp.messages_in is not None for sp in spans)


def test_ingest_with_pii_tag_redacts() -> None:
    client = _client()
    _, _proj, api_key, _ = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-pii", tags={"pii": True})
    assert ingest["ingested"] == 1
    trace_id = ingest["results"][0]["trace_id"]
    with SessionLocal() as db:
        t = db.get(Trace, trace_id)
        assert t.redacted
        spans = db.query(Span).filter(Span.trace_id == trace_id).all()
        for sp in spans:
            assert sp.messages_in is None
            assert sp.messages_out is None
            assert sp.input is None
            assert sp.output is None


def test_ingest_with_redact_header_redacts() -> None:
    client = _client()
    _, _proj, api_key, _ = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-hdr-redact", extra_headers={"X-EvalOps-Redact": "1"})
    assert ingest["ingested"] == 1
    trace_id = ingest["results"][0]["trace_id"]
    with SessionLocal() as db:
        t = db.get(Trace, trace_id)
        assert t.redacted
        spans = db.query(Span).filter(Span.trace_id == trace_id).all()
        for sp in spans:
            assert sp.messages_in is None


def test_get_redacted_trace_does_not_expose_messages() -> None:
    client = _client()
    _, _proj, api_key, headers = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-get-redact", tags={"pii": True})
    trace_id = ingest["results"][0]["trace_id"]
    detail = client.get(f"/v1/traces/{trace_id}", headers=headers).json()
    assert detail["trace"]["redacted"] is True
    for sp in detail["spans"]:
        assert sp["messages_in"] is None
        assert sp["messages_out"] is None


# ── G-09 / G-10: Export download + absolute path ─────────────────────────────

def test_create_and_download_export() -> None:
    client = _client()
    _, project_id, api_key, headers = _bootstrap(client)
    _ingest(client, api_key, "ct-export-dl")
    exp_res = client.post(
        "/v1/exports", headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {}},
    )
    assert exp_res.status_code == 202, exp_res.text
    export_id = exp_res.json()["export_id"]
    dl_res = client.get(f"/v1/exports/{export_id}/download", headers=headers)
    assert dl_res.status_code == 200, dl_res.text
    ct = dl_res.headers.get("content-type", "")
    assert "ndjson" in ct or "json" in ct
    lines = [ln for ln in dl_res.text.strip().split("\n") if ln]
    assert len(lines) >= 1
    data = json.loads(lines[0])
    assert "id" in data


def test_download_expired_export_returns_410() -> None:
    client = _client()
    _, project_id, _, headers = _bootstrap(client)
    exp_res = client.post(
        "/v1/exports", headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {}},
    )
    export_id = exp_res.json()["export_id"]
    with SessionLocal() as db:
        job = db.get(ExportJob, export_id)
        job.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    dl_res = client.get(f"/v1/exports/{export_id}/download", headers=headers)
    assert dl_res.status_code == 410, dl_res.text


def test_export_path_is_absolute(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EVALOPS_EXPORTS_DIR", str(tmp_path / "exports"))
    client = _client()
    _, project_id, _, headers = _bootstrap(client)
    exp_res = client.post(
        "/v1/exports", headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {}},
    )
    assert exp_res.status_code == 202, exp_res.text
    export_id = exp_res.json()["export_id"]
    with SessionLocal() as db:
        job = db.get(ExportJob, export_id)
        p = Path(job.file_path)
        assert p.is_absolute(), f"file_path not absolute: {job.file_path}"
        assert p.exists(), f"export file not found: {job.file_path}"
        assert str(tmp_path) in str(p)


def test_download_does_not_expose_local_path() -> None:
    client = _client()
    _, project_id, _, headers = _bootstrap(client)
    exp_res = client.post(
        "/v1/exports", headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {}},
    )
    export_id = exp_res.json()["export_id"]
    dl_res = client.get(f"/v1/exports/{export_id}/download", headers=headers)
    assert dl_res.status_code == 200
    cd = dl_res.headers.get("content-disposition", "")
    assert "storage" not in cd
    assert "\\" not in cd
    assert "/" not in cd or "export-" in cd  # only the safe filename


# ── G-21: Soft delete ─────────────────────────────────────────────────────────

def test_soft_delete_sets_deleted_at() -> None:
    client = _client()
    _, _proj, api_key, headers = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-softdel")
    trace_id = ingest["results"][0]["trace_id"]
    res = client.delete(f"/v1/traces/{trace_id}", headers=headers)
    assert res.status_code == 204
    with SessionLocal() as db:
        t = db.get(Trace, trace_id)
        assert t is not None, "row must still exist (soft delete)"
        assert t.deleted_at is not None


def test_list_traces_excludes_deleted() -> None:
    client = _client()
    _, project_id, api_key, headers = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-list-excl")
    trace_id = ingest["results"][0]["trace_id"]
    client.delete(f"/v1/traces/{trace_id}", headers=headers)
    list_res = client.get(f"/v1/traces?project_id={project_id}", headers=headers)
    assert list_res.status_code == 200
    ids = [t["id"] for t in list_res.json()["data"]]
    assert trace_id not in ids


def test_get_deleted_trace_returns_404() -> None:
    client = _client()
    _, _proj, api_key, headers = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-get-del")
    trace_id = ingest["results"][0]["trace_id"]
    client.delete(f"/v1/traces/{trace_id}", headers=headers)
    get_res = client.get(f"/v1/traces/{trace_id}", headers=headers)
    assert get_res.status_code == 404


def test_double_delete_returns_404() -> None:
    client = _client()
    _, _proj, api_key, headers = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-double-del")
    trace_id = ingest["results"][0]["trace_id"]
    first = client.delete(f"/v1/traces/{trace_id}", headers=headers)
    assert first.status_code == 204
    second = client.delete(f"/v1/traces/{trace_id}", headers=headers)
    assert second.status_code == 404


# ── Fix-7B.1: soft delete consistency ─────────────────────────────────────────

def test_export_excludes_soft_deleted_trace() -> None:
    client = _client()
    _, project_id, api_key, headers = _bootstrap(client)
    active = _ingest(client, api_key, "ct-exp-active")["results"][0]["trace_id"]
    deleted = _ingest(client, api_key, "ct-exp-deleted")["results"][0]["trace_id"]
    assert client.delete(f"/v1/traces/{deleted}", headers=headers).status_code == 204

    exp_res = client.post(
        "/v1/exports", headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {}},
    )
    assert exp_res.status_code == 202, exp_res.text
    export_id = exp_res.json()["export_id"]

    with SessionLocal() as db:
        job = db.get(ExportJob, export_id)
        assert job.row_count == 1, "row_count must count only active traces"

    dl_res = client.get(f"/v1/exports/{export_id}/download", headers=headers)
    assert dl_res.status_code == 200, dl_res.text
    lines = [json.loads(ln) for ln in dl_res.text.strip().split("\n") if ln]
    ids = [row["id"] for row in lines]
    assert active in ids
    assert deleted not in ids


def test_reingest_deleted_client_trace_id_returns_409() -> None:
    client = _client()
    _, _proj, api_key, headers = _bootstrap(client)
    ingest = _ingest(client, api_key, "ct-reingest-del")
    trace_id = ingest["results"][0]["trace_id"]
    assert client.delete(f"/v1/traces/{trace_id}", headers=headers).status_code == 204

    t0, t1 = _ts()
    payload = {
        "traces": [{
            "client_trace_id": "ct-reingest-del",
            "name": "test.trace",
            "environment": "prod",
            "started_at": t0,
            "ended_at": t1,
            "status": "ok",
            "tags": {},
            "spans": [],
        }]
    }
    res = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["error"] == "trace_deleted"
    assert detail["client_trace_id"] == "ct-reingest-del"

    with SessionLocal() as db:
        rows = (
            db.query(Trace)
            .filter(Trace.client_trace_id == "ct-reingest-del")
            .all()
        )
        assert len(rows) == 1, "must not create a new trace row"
        assert rows[0].id == trace_id
        assert rows[0].deleted_at is not None


def test_reingest_active_client_trace_id_still_idempotent() -> None:
    client = _client()
    _, _proj, api_key, headers = _bootstrap(client)
    first = _ingest(client, api_key, "ct-reingest-active")["results"][0]["trace_id"]
    second = _ingest(client, api_key, "ct-reingest-active")["results"][0]["trace_id"]
    assert first == second


# ── A-13: redaction opt-in extended PII surface ──────────────────────────────

def _rich_payload(client_trace_id: str, tags: dict) -> dict:
    t0, t1 = _ts()
    return {
        "traces": [{
            "client_trace_id": client_trace_id,
            "name": "rich.trace",
            "environment": "prod",
            "started_at": t0,
            "ended_at": t1,
            "status": "ok",
            "tags": tags,
            "user_ref": "user@example.com",
            "metadata": {"ssn": "123-45-6789"},
            "spans": [{
                "client_span_id": "sp1",
                "type": "llm_call",
                "name": "span",
                "started_at": t0,
                "ended_at": t1,
                "status": "ok",
                "messages_in": [{"role": "user", "content": "card 4111111111111111"}],
                "messages_out": [{"role": "assistant", "content": "ok"}],
                "input": {"text": "pii in"},
                "output": {"text": "pii out"},
                "error": {"detail": "boom with internal info"},
                "metadata": {"customer_email": "c@acme.com"},
                "events": [{
                    "type": "log",
                    "occurred_at": t0,
                    "payload": {"email": "leak@acme.com"},
                }],
            }],
        }]
    }


def test_redaction_clears_extended_pii_surface() -> None:
    client = _client()
    _, _proj, api_key, _ = _bootstrap(client)
    payload = _rich_payload("ct-rich-pii", tags={"pii": True, "customer": "acme"})
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload).json()
    assert resp["ingested"] == 1
    trace_id = resp["results"][0]["trace_id"]
    with SessionLocal() as db:
        t = db.get(Trace, trace_id)
        assert t.redacted is True
        assert t.tags == {}
        assert t.user_ref is None
        assert t.metadata_json == {}
        spans = db.query(Span).filter(Span.trace_id == trace_id).all()
        assert spans
        for sp in spans:
            assert sp.messages_in is None
            assert sp.messages_out is None
            assert sp.input is None
            assert sp.output is None
            assert sp.error is None
            assert sp.metadata_json == {}
            for ev in db.query(Event).filter(Event.span_id == sp.id).all():
                assert ev.payload == {}


def test_no_redaction_preserves_extended_fields() -> None:
    client = _client()
    _, _proj, api_key, _ = _bootstrap(client)
    payload = _rich_payload("ct-rich-plain", tags={"customer": "acme"})
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload).json()
    trace_id = resp["results"][0]["trace_id"]
    with SessionLocal() as db:
        t = db.get(Trace, trace_id)
        assert t.redacted is False
        assert t.user_ref == "user@example.com"
        assert t.metadata_json == {"ssn": "123-45-6789"}
        assert t.tags == {"customer": "acme"}
        sp = db.query(Span).filter(Span.trace_id == trace_id).first()
        assert sp.messages_in is not None
        assert sp.error == {"detail": "boom with internal info"}
        # The trace ingest pipeline adds `_cost_source` to span metadata; the
        # contract for callers is "user keys preserved untouched". Filter the
        # system prefix before equality, but assert it carries an expected value.
        user_metadata = {k: v for k, v in sp.metadata_json.items() if not k.startswith("_")}
        assert user_metadata == {"customer_email": "c@acme.com"}
        assert sp.metadata_json.get("_cost_source") in {"priced", "estimated", "unknown", "provided"}
        ev = db.query(Event).join(Span).filter(Span.trace_id == trace_id).first()
        assert ev.payload == {"email": "leak@acme.com"}


# ── A-12: internal errors never leak through public responses ────────────────

_LEAK = (
    "(sqlite3.OperationalError) no such table [SQL: SELECT * FROM traces] "
    "/home/app/.venv/x.py token eyJabc12345.def67890ZZ.sig key evk_prod_deadbeef"
)


def test_ingest_internal_error_is_sanitized(monkeypatch) -> None:
    client = _client()
    _, _proj, api_key, _ = _bootstrap(client)

    import app.domain.services.trace_ingest_service as svc

    def _boom(*_a, **_k):
        raise RuntimeError(_LEAK)

    monkeypatch.setattr(svc, "_persist_trace", _boom)
    res = client.post(
        "/v1/traces", headers={"X-EvalOps-Key": api_key},
        json=_rich_payload("ct-boom", tags={}),
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["ingested"] == 0
    assert body["errors"][0]["message"] == "ingest_failed"
    blob = res.text
    for needle in ("sqlite3", "SELECT", ".venv", "eyJabc", "evk_prod"):
        assert needle not in blob


def test_export_internal_error_is_sanitized(monkeypatch) -> None:
    client = _client()
    _, project_id, api_key, headers = _bootstrap(client)
    _ingest(client, api_key, "ct-exp-boom")

    import app.domain.services.export_service as svc

    def _boom(*_a, **_k):
        raise RuntimeError(_LEAK)

    monkeypatch.setattr(svc, "_filter_traces", _boom)
    res = client.post(
        "/v1/exports", headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {}},
    )
    assert res.status_code == 500
    assert res.json()["detail"] == "export_failed"
    assert "sqlite3" not in res.text and "evk_prod" not in res.text
    with SessionLocal() as db:
        job = db.query(ExportJob).filter(ExportJob.project_id == project_id).one()
        assert job.status == "error"
        assert job.error == "export_failed"
