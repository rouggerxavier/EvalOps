import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Organization, User
from app.schemas import ApiKeyOut, OrganizationOut, QualityGateConfigOut, TraceIn, TraceOut
from app.security import create_access_token


def _assert_utc(value: str) -> None:
    assert datetime.fromisoformat(value).utcoffset() == timedelta(0), value


def test_sqlite_server_timestamp_model_dump_and_json() -> None:
    with SessionLocal() as db:
        org = Organization(id="org", name="Acme", slug="acme")
        db.add(org)
        db.commit()
        db.refresh(org)
        assert org.created_at.tzinfo is None  # SQLite drops the UTC offset.
        out = OrganizationOut.model_validate(org)
        assert out.model_dump()["created_at"].utcoffset() == timedelta(0)
        _assert_utc(json.loads(out.model_dump_json())["created_at"])


def test_server_timestamps_preserve_aware_offsets_and_nulls() -> None:
    aware = datetime(2026, 11, 8, 9, tzinfo=timezone(timedelta(hours=-3)))
    out = OrganizationOut(id="org", name="Acme", slug="acme", created_at=aware)
    assert out.created_at is aware
    assert out.model_dump()["created_at"].timestamp() == aware.timestamp()
    assert json.loads(out.model_dump_json())["created_at"].endswith("-03:00")
    config = QualityGateConfigOut(project_id="prj", configured=False, updated_at=None)
    assert config.model_dump()["updated_at"] is None
    assert json.loads(config.model_dump_json())["updated_at"] is None


def test_client_timestamps_are_not_relabelled() -> None:
    naive = datetime(2026, 11, 8, 9)
    trace_in = TraceIn(name="client", environment="prod", status="ok", started_at=naive, ended_at=naive)
    trace = TraceOut(
        id="tr", project_id="prj", organization_id="org", name="client", environment="prod", status="ok",
        started_at=trace_in.started_at, ended_at=trace_in.ended_at, duration_ms=0,
        total_tokens_in=0, total_tokens_out=0, total_cost_usd=0, tags={}, metadata_json={}, created_at=naive,
    )
    assert trace.started_at.tzinfo is None
    assert trace.ended_at.tzinfo is None
    key = ApiKeyOut(id="key", prefix="key", name="test", environment="prod", scopes=[],
                    rate_limit_per_minute=1, created_at=naive, expires_at=naive)
    assert key.expires_at.tzinfo is None
    assert key.revoked_at is None


def test_sqlite_http_and_export_server_timestamps(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.domain.services.export_service.exports_dir", lambda: tmp_path)
    client = TestClient(app)
    with SessionLocal() as db:
        db.add(User(id="usr", email="user@example.com", name="User"))
        db.commit()
    headers = {"Authorization": f"Bearer {create_access_token(sub='usr', email='user@example.com', name='User')}"}
    org_response = client.post("/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"})
    assert org_response.status_code == 201, org_response.text
    org = org_response.json()
    _assert_utc(org["created_at"])
    _assert_utc(client.get("/v1/me", headers=headers).json()["organizations"][0]["created_at"])
    project = client.post("/v1/projects", headers=headers, json={
        "organization_id": org["id"], "name": "Project", "slug": "project",
    }).json()
    key = client.post(f"/v1/projects/{project['id']}/api-keys", headers=headers, json={
        "name": "ingest", "environment": "prod",
    }).json()["key"]
    ingested = client.post("/v1/traces", headers={"X-EvalOps-Key": key}, json={"traces": [{
        "name": "client", "environment": "prod", "status": "ok",
        "started_at": "2026-11-08T09:00:00-03:00", "ended_at": "2026-11-08T09:00:01-03:00",
    }]})
    assert ingested.status_code == 202, ingested.text
    trace_id = ingested.json()["results"][0]["trace_id"]
    feedback = client.post(f"/v1/traces/{trace_id}/feedback", headers=headers, json={"thumbs": "down"})
    assert feedback.status_code == 201, feedback.text
    _assert_utc(feedback.json()["feedback"]["created_at"])
    flag = client.post(f"/v1/traces/{trace_id}/flags", headers=headers, json={"reason": "low_quality"})
    assert flag.status_code == 201, flag.text
    _assert_utc(flag.json()["created_at"])
    detail = client.get(f"/v1/traces/{trace_id}", headers=headers).json()
    for record in (detail["trace"], detail["feedback"][0], detail["flags"][0]):
        _assert_utc(record["created_at"])
    # Historical client wall-clock values must not gain an assumed UTC offset.
    assert datetime.fromisoformat(detail["trace"]["started_at"]).tzinfo is None
    subscription = client.get(f"/v1/organizations/{org['id']}/subscription", headers=headers).json()["subscription"]
    _assert_utc(subscription["started_at"])
    assert subscription["ends_at"] is None
    exported = client.post("/v1/exports", headers=headers, json={"project_id": project["id"], "format": "jsonl"})
    assert exported.status_code == 202, exported.text
    job = client.get(f"/v1/exports/{exported.json()['export_id']}", headers=headers).json()
    for field in ("created_at", "completed_at", "expires_at"):
        _assert_utc(job[field])
    row = json.loads(Path(job["file_path"]).read_text().strip())
    _assert_utc(row["feedback"][0]["created_at"])
