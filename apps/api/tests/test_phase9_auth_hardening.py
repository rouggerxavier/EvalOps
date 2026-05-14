"""Phase 2 auth hardening tests (G-01/G-13/G-15/G-16)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.domain.services.rate_limit_service import reset_all
from app.main import app
from app.models import ApiKey, AuditLog, RevokedToken, User
from app.security import create_access_token, hash_password, new_id


@pytest.fixture(autouse=True)
def _reset():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    reset_all()
    yield
    reset_all()
    Base.metadata.drop_all(bind=engine)


def _client() -> TestClient:
    return TestClient(app)


# --- bootstrap helpers ------------------------------------------------------


def _register_user(client: TestClient, email: str = "u@example.com", password: str = "Sup3rSecret!") -> dict:
    res = client.post(
        "/v1/auth/register",
        json={"email": email, "name": "User", "password": password},
    )
    assert res.status_code == 201, res.text
    return res.json()


def _bootstrap_api_key(
    client: TestClient,
    user_token: str,
    org_id: str,
    project_id: str,
    *,
    name: str = "ingest-key",
    rate_limit: int | None = None,
) -> str:
    payload = {"name": name, "environment": "prod", "scopes": ["ingest", "read"]}
    res = client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers={"Authorization": f"Bearer {user_token}"},
        json=payload,
    )
    assert res.status_code in (200, 201), res.text
    key = res.json()["key"]

    if rate_limit is not None:
        with SessionLocal() as db:
            row = db.query(ApiKey).filter(ApiKey.project_id == project_id).order_by(ApiKey.created_at.desc()).first()
            assert row is not None
            row.rate_limit_per_minute = rate_limit
            db.add(row)
            db.commit()
    return key


def _trace_payload(client_trace_id: str) -> dict:
    t0 = datetime.now(timezone.utc)
    t1 = t0 + timedelta(seconds=1)
    return {
        "traces": [
            {
                "client_trace_id": client_trace_id,
                "name": "p9.test",
                "service": "svc",
                "environment": "prod",
                "started_at": t0.isoformat(),
                "ended_at": t1.isoformat(),
                "status": "ok",
                "tags": {},
                "user_ref": None,
                "metadata": {},
                "spans": [],
            }
        ]
    }


# ---------------------------------------------------------------- G-01 -----


def test_api_key_rate_limit_returns_429_after_cap() -> None:
    client = _client()
    auth = _register_user(client)
    org_id = auth["workspace"]["org_id"]
    project_id = auth["workspace"]["project_id"]
    api_key = _bootstrap_api_key(client, auth["token"], org_id, project_id, rate_limit=3)

    for i in range(3):
        ok = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=_trace_payload(f"ct_{i}"))
        assert ok.status_code == 202, ok.text

    blocked = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=_trace_payload("ct_blocked"))
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "too_many_requests"
    assert "Retry-After" in blocked.headers


def test_api_key_rate_limit_uses_default_when_column_null() -> None:
    client = _client()
    auth = _register_user(client)
    org_id = auth["workspace"]["org_id"]
    project_id = auth["workspace"]["project_id"]
    api_key = _bootstrap_api_key(client, auth["token"], org_id, project_id)

    # Force the column to a non-positive sentinel; service should fall back to 60.
    with SessionLocal() as db:
        row = db.query(ApiKey).filter(ApiKey.project_id == project_id).first()
        row.rate_limit_per_minute = 0
        db.add(row)
        db.commit()

    # 60 default — a handful of calls must NOT trip the limiter.
    for i in range(5):
        res = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=_trace_payload(f"ct_def_{i}"))
        assert res.status_code == 202, res.text


def test_api_key_rate_limit_buckets_are_independent() -> None:
    client = _client()
    auth = _register_user(client)
    org_id = auth["workspace"]["org_id"]
    project_id = auth["workspace"]["project_id"]
    key_a = _bootstrap_api_key(client, auth["token"], org_id, project_id, name="key-A", rate_limit=2)
    key_b = _bootstrap_api_key(client, auth["token"], org_id, project_id, name="key-B", rate_limit=2)

    for i in range(2):
        assert (
            client.post("/v1/traces", headers={"X-EvalOps-Key": key_a}, json=_trace_payload(f"ka_{i}")).status_code
            == 202
        )

    blocked = client.post("/v1/traces", headers={"X-EvalOps-Key": key_a}, json=_trace_payload("ka_3"))
    assert blocked.status_code == 429

    # Key B still has full budget.
    ok_b = client.post("/v1/traces", headers={"X-EvalOps-Key": key_b}, json=_trace_payload("kb_1"))
    assert ok_b.status_code == 202


# ---------------------------------------------------------------- G-13 -----


def test_login_blocks_after_five_failures() -> None:
    client = _client()
    _register_user(client, email="bf@example.com", password="Correct1!")
    for _ in range(5):
        res = client.post("/v1/auth/login", json={"email": "bf@example.com", "password": "Wrong1!!"})
        assert res.status_code == 401

    blocked = client.post("/v1/auth/login", json={"email": "bf@example.com", "password": "Wrong1!!"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_login_failure_does_not_reveal_email_existence() -> None:
    client = _client()
    _register_user(client, email="real@example.com", password="Correct1!")

    bad_real = client.post("/v1/auth/login", json={"email": "real@example.com", "password": "Wrong1!!"})
    bad_fake = client.post("/v1/auth/login", json={"email": "ghost@example.com", "password": "Wrong1!!"})

    assert bad_real.status_code == 401
    assert bad_fake.status_code == 401
    assert bad_real.json()["detail"] == "invalid_credentials"
    assert bad_fake.json()["detail"] == "invalid_credentials"
    assert bad_real.json() == bad_fake.json()


def test_successful_login_resets_failure_window() -> None:
    client = _client()
    _register_user(client, email="ok@example.com", password="Correct1!")

    for _ in range(4):
        bad = client.post("/v1/auth/login", json={"email": "ok@example.com", "password": "Wrong1!!"})
        assert bad.status_code == 401

    good = client.post("/v1/auth/login", json={"email": "ok@example.com", "password": "Correct1!"})
    assert good.status_code == 200

    # Window cleared; 4 more failures must still be allowed (would 429 only at the 5th in current window).
    for _ in range(4):
        again = client.post("/v1/auth/login", json={"email": "ok@example.com", "password": "Wrong1!!"})
        assert again.status_code == 401


# ---------------------------------------------------------------- G-15 -----


def test_logout_invalidates_token_for_subsequent_requests() -> None:
    client = _client()
    auth = _register_user(client, email="lo@example.com", password="Correct1!")
    token = auth["token"]

    pre = client.get("/v1/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert pre.status_code == 200

    bye = client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert bye.status_code == 204

    post = client.get("/v1/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert post.status_code == 401


def test_logout_persists_jti_in_revoked_tokens() -> None:
    client = _client()
    auth = _register_user(client, email="rt@example.com", password="Correct1!")
    token = auth["token"]

    res = client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 204
    with SessionLocal() as db:
        rows = db.query(RevokedToken).all()
        assert len(rows) == 1
        assert rows[0].expires_at is not None


def test_logout_is_idempotent() -> None:
    client = _client()
    auth = _register_user(client, email="id@example.com", password="Correct1!")
    token = auth["token"]

    first = client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    second = client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 204
    assert second.status_code == 204
    with SessionLocal() as db:
        assert db.query(RevokedToken).count() == 1


def test_logout_without_token_returns_204() -> None:
    client = _client()
    res = client.post("/v1/auth/logout")
    assert res.status_code == 204
    res_bad = client.post("/v1/auth/logout", headers={"Authorization": "Bearer notajwt"})
    assert res_bad.status_code == 204


def test_legacy_token_without_jti_still_works_until_exp() -> None:
    """Documented behaviour: pre-Phase-2 tokens have no jti and bypass the
    denylist. They continue to work until natural expiry."""
    client = _client()
    with SessionLocal() as db:
        db.add(User(id="usr_legacy", email="legacy@example.com", name="Legacy", password_hash=hash_password("x")))
        db.commit()

    # Build a JWT manually without jti.
    import jwt as _jwt
    from app.security import JWT_ALGORITHM, JWT_SECRET

    now = datetime.now(timezone.utc)
    legacy_token = _jwt.encode(
        {"sub": "usr_legacy", "email": "legacy@example.com", "name": "Legacy",
         "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=10)).timestamp())},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    res = client.get("/v1/auth/session", headers={"Authorization": f"Bearer {legacy_token}"})
    assert res.status_code == 200


# ---------------------------------------------------------------- G-16 -----


def test_failed_login_creates_audit_row() -> None:
    client = _client()
    _register_user(client, email="ad@example.com", password="Correct1!")
    client.post("/v1/auth/login", json={"email": "ad@example.com", "password": "Wrong1!!"})

    with SessionLocal() as db:
        rows = db.query(AuditLog).filter(AuditLog.action == "auth.failed_login").all()
        assert len(rows) == 1
        payload = rows[0].payload
        assert payload["email"] == "ad@example.com"
        assert "ip" in payload
        assert payload["reason"] == "invalid_credentials"
        assert rows[0].organization_id is None
        assert "password" not in payload
        assert "token" not in payload


def test_failed_login_audits_nonexistent_email_too() -> None:
    client = _client()
    client.post("/v1/auth/login", json={"email": "nobody@example.com", "password": "Wrong1!!"})
    with SessionLocal() as db:
        rows = db.query(AuditLog).filter(AuditLog.action == "auth.failed_login").all()
        assert len(rows) == 1
        assert rows[0].payload["email"] == "nobody@example.com"


def test_successful_login_does_not_create_failed_audit() -> None:
    client = _client()
    _register_user(client, email="happy@example.com", password="Correct1!")
    good = client.post("/v1/auth/login", json={"email": "happy@example.com", "password": "Correct1!"})
    assert good.status_code == 200
    with SessionLocal() as db:
        assert db.query(AuditLog).filter(AuditLog.action == "auth.failed_login").count() == 0
