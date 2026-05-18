"""Phase 7E backend API key expiration tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.domain.services.rate_limit_service import reset_all
from app.main import app
from app.models import ApiKey


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


def _register(client: TestClient) -> dict:
    response = client.post(
        "/v1/auth/register",
        json={"email": "phase7e@example.com", "name": "Phase 7E", "password": "Sup3rSecret!"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _trace_payload(client_trace_id: str) -> dict:
    started_at = datetime.now(timezone.utc)
    ended_at = started_at + timedelta(milliseconds=100)
    return {
        "traces": [
            {
                "client_trace_id": client_trace_id,
                "name": "phase7e.trace",
                "service": "phase7e",
                "environment": "prod",
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "status": "ok",
                "tags": {},
                "spans": [],
            }
        ]
    }


def _create_key(
    client: TestClient,
    token: str,
    project_id: str,
    *,
    expires_at: datetime | None = None,
) -> dict:
    payload: dict = {"name": "phase7e-key", "environment": "prod", "scopes": ["ingest", "read"]}
    if expires_at is not None:
        payload["expires_at"] = expires_at.isoformat()
    response = client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _set_key_expiry(
    key_id: str,
    *,
    expires_at: datetime | None,
    rate_limit_per_minute: int | None = None,
) -> None:
    with SessionLocal() as db:
        key = db.get(ApiKey, key_id)
        assert key is not None
        key.expires_at = expires_at
        if rate_limit_per_minute is not None:
            key.rate_limit_per_minute = rate_limit_per_minute
        db.add(key)
        db.commit()


def _read_key(key_id: str) -> ApiKey:
    with SessionLocal() as db:
        key = db.get(ApiKey, key_id)
        assert key is not None
        db.expunge(key)
        return key


def test_api_key_without_expiration_still_ingests_and_lists_null_expiry() -> None:
    client = _client()
    auth = _register(client)
    token = auth["token"]
    project_id = auth["workspace"]["project_id"]

    created = _create_key(client, token, project_id)
    assert created["expires_at"] is None

    ingest = client.post("/v1/traces", headers={"X-EvalOps-Key": created["key"]}, json=_trace_payload("ct_no_exp"))
    assert ingest.status_code == 202, ingest.text

    listed = client.get(f"/v1/projects/{project_id}/api-keys", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["data"] if item["id"] == created["id"])
    assert row["expires_at"] is None
    assert "key" not in row


def test_api_key_with_future_expiration_ingests_and_returns_expiry() -> None:
    client = _client()
    auth = _register(client)
    token = auth["token"]
    project_id = auth["workspace"]["project_id"]
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    created = _create_key(client, token, project_id, expires_at=expires_at)

    assert created["expires_at"] is not None
    ingest = client.post("/v1/traces", headers={"X-EvalOps-Key": created["key"]}, json=_trace_payload("ct_future"))
    assert ingest.status_code == 202, ingest.text

    listed = client.get(f"/v1/projects/{project_id}/api-keys", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200, listed.text
    row = next(item for item in listed.json()["data"] if item["id"] == created["id"])
    assert row["expires_at"] is not None


def test_expired_api_key_is_unauthorized_without_last_used_or_rate_limit_hit() -> None:
    client = _client()
    auth = _register(client)
    created = _create_key(client, auth["token"], auth["workspace"]["project_id"])
    key_id = created["id"]

    _set_key_expiry(
        key_id,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        rate_limit_per_minute=1,
    )
    expired = client.post("/v1/traces", headers={"X-EvalOps-Key": created["key"]}, json=_trace_payload("ct_expired"))
    assert expired.status_code == 401
    assert expired.json()["detail"] == "unauthorized"
    assert _read_key(key_id).last_used_at is None

    _set_key_expiry(key_id, expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
    allowed = client.post("/v1/traces", headers={"X-EvalOps-Key": created["key"]}, json=_trace_payload("ct_after"))
    assert allowed.status_code == 202, allowed.text


def test_create_api_key_rejects_past_expiration() -> None:
    client = _client()
    auth = _register(client)
    response = client.post(
        f"/v1/projects/{auth['workspace']['project_id']}/api-keys",
        headers={"Authorization": f"Bearer {auth['token']}"},
        json={
            "name": "expired-key",
            "environment": "prod",
            "scopes": ["ingest", "read"],
            "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        },
    )

    assert response.status_code == 422


def test_create_api_key_rejects_current_expiration() -> None:
    client = _client()
    auth = _register(client)
    response = client.post(
        f"/v1/projects/{auth['workspace']['project_id']}/api-keys",
        headers={"Authorization": f"Bearer {auth['token']}"},
        json={
            "name": "current-expiry-key",
            "environment": "prod",
            "scopes": ["ingest", "read"],
            "expires_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    assert response.status_code == 422


def test_revoked_future_api_key_still_rejects_ingest() -> None:
    client = _client()
    auth = _register(client)
    project_id = auth["workspace"]["project_id"]
    created = _create_key(
        client,
        auth["token"],
        project_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    revoked = client.post(
        f"/v1/projects/{project_id}/api-keys/{created['id']}/revoke",
        headers={"Authorization": f"Bearer {auth['token']}"},
    )
    assert revoked.status_code == 204

    ingest = client.post("/v1/traces", headers={"X-EvalOps-Key": created["key"]}, json=_trace_payload("ct_revoked"))
    assert ingest.status_code == 401
    assert ingest.json()["detail"] == "unauthorized"
