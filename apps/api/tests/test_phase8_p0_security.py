"""Phase 1 P0 security tests (G-17): payload size + spans-per-trace caps.

Frontend gaps (G-02, G-03, G-04) are covered by node:test in apps/web/tests/.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import create_access_token


def _client() -> TestClient:
    return TestClient(app)


def _auth_header(user_id: str = "usr_p8", email: str = "p8@example.com") -> dict[str, str]:
    token = create_access_token(sub=user_id, email=email, name="Phase8")
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> tuple[str, str]:
    with SessionLocal() as db:
        db.add(User(id="usr_p8", email="p8@example.com", name="Phase8"))
        db.commit()
    headers = _auth_header()
    org = client.post("/v1/organizations", headers=headers, json={"name": "AcmeP8", "slug": "acme-p8"}).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={"organization_id": org["id"], "name": "P8", "slug": "p8"},
    ).json()
    key = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()["key"]
    return project["id"], key


def _span(idx: int, t0: datetime) -> dict:
    s0 = t0 + timedelta(milliseconds=idx * 2)
    s1 = s0 + timedelta(milliseconds=1)
    return {
        "client_span_id": f"cs_{idx}",
        "type": "llm_call",
        "name": "openai.chat.completions",
        "started_at": s0.isoformat(),
        "ended_at": s1.isoformat(),
        "status": "ok",
    }


def _trace_payload(client_trace_id: str, span_count: int = 1) -> dict:
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(seconds=2)
    return {
        "traces": [
            {
                "client_trace_id": client_trace_id,
                "name": "p8.test",
                "service": "svc",
                "environment": "prod",
                "started_at": t0.isoformat(),
                "ended_at": t1.isoformat(),
                "status": "ok",
                "tags": {},
                "user_ref": None,
                "metadata": {},
                "spans": [_span(i, t0) for i in range(span_count)],
            }
        ]
    }


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("EVALOPS_MAX_BODY_BYTES", raising=False)
    monkeypatch.delenv("EVALOPS_MAX_SPANS_PER_TRACE", raising=False)
    yield


def test_normal_ingest_passes_with_defaults() -> None:
    client = _client()
    _, api_key = _bootstrap(client)
    res = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=_trace_payload("ct_ok"))
    assert res.status_code == 202, res.text
    assert res.json()["ingested"] == 1


def test_payload_over_max_body_bytes_returns_413(monkeypatch) -> None:
    monkeypatch.setenv("EVALOPS_MAX_BODY_BYTES", "1024")  # 1 KB cap
    client = _client()
    _, api_key = _bootstrap(client)
    payload = _trace_payload("ct_big", span_count=200)
    res = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert res.status_code == 413, res.text
    body = res.json()
    assert body["detail"] == "payload_too_large"
    assert body["limit_bytes"] == 1024


def test_trace_over_max_spans_returns_422(monkeypatch) -> None:
    monkeypatch.setenv("EVALOPS_MAX_SPANS_PER_TRACE", "5")
    client = _client()
    _, api_key = _bootstrap(client)
    payload = _trace_payload("ct_many_spans", span_count=10)
    res = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert detail["error"] == "too_many_spans"
    assert detail["spans"] == 10
    assert detail["limit"] == 5
    assert detail["trace_index"] == 0
    assert detail["client_trace_id"] == "ct_many_spans"


def test_max_spans_is_env_configurable(monkeypatch) -> None:
    monkeypatch.setenv("EVALOPS_MAX_SPANS_PER_TRACE", "20")
    client = _client()
    _, api_key = _bootstrap(client)

    ok = client.post(
        "/v1/traces",
        headers={"X-EvalOps-Key": api_key},
        json=_trace_payload("ct_under_cap", span_count=15),
    )
    assert ok.status_code == 202, ok.text

    over = client.post(
        "/v1/traces",
        headers={"X-EvalOps-Key": api_key},
        json=_trace_payload("ct_over_cap", span_count=25),
    )
    assert over.status_code == 422
    assert over.json()["detail"]["limit"] == 20


def test_default_body_size_permits_normal_payload() -> None:
    from app.config import DEFAULT_MAX_BODY_BYTES, max_body_bytes

    assert max_body_bytes() == DEFAULT_MAX_BODY_BYTES == 8 * 1024 * 1024

    client = _client()
    _, api_key = _bootstrap(client)
    payload = _trace_payload("ct_default", span_count=50)
    res = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert res.status_code == 202, res.text
    assert res.json()["ingested"] == 1


# ── A-12: public error sanitization (app.safe_errors.safe_message) ────────────

@pytest.mark.parametrize(
    "leak",
    [
        "(sqlite3.OperationalError) no such table: traces",
        "sqlalchemy.exc.IntegrityError: UNIQUE constraint failed",
        "Traceback (most recent call last):\n  File \"/app/x.py\", line 4, in run",
        'File "/home/app/.venv/lib/svc.py", line 12, in handler',
        "SELECT secret FROM users WHERE id = '1'",
        "psycopg2.errors.UndefinedColumn: column does not exist",
        "no such table: traces",
        "UNIQUE constraint failed: users.email",
        'relation "traces" does not exist',
        "auth failed for bearer eyJhbGciOiJ.eyJzdWIiOiIx.sig",
        "leaked api key evk_prod_abcdef123456",
        "provider key sk-proj-abc123456789xyz leaked",
        "C:\\Users\\svc\\app\\db.py crashed",
        "password=hunter2 in connection string",
        "x" * 250,
    ],
)
def test_safe_message_collapses_leaky_strings(leak: str) -> None:
    from app.safe_errors import GENERIC_ERROR, safe_message

    assert safe_message(Exception(leak), fallback="op_failed") == "op_failed"
    assert safe_message(leak) == GENERIC_ERROR
    assert leak not in safe_message(Exception(leak), fallback="op_failed")


@pytest.mark.parametrize(
    "safe",
    [
        "ended_at must be >= started_at",
        "unknown top-level fields: ['foo']",
        "rubric_slug_taken",
        "baseline variant must exist in variants",
    ],
)
def test_safe_message_passes_through_vetted_validation_text(safe: str) -> None:
    from app.safe_errors import safe_message

    assert safe_message(ValueError(safe), fallback="invalid") == safe


def test_is_safe_public_text_rejects_empty_and_long() -> None:
    from app.safe_errors import is_safe_public_text

    assert is_safe_public_text("short and clean") is True
    assert is_safe_public_text("") is False
    assert is_safe_public_text("a" * 201) is False
