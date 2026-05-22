from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Trace, User
from app.security import create_access_token


def _auth_header(user_id: str, email: str, name: str) -> dict[str, str]:
    token = create_access_token(sub=user_id, email=email, name=name)
    return {"Authorization": f"Bearer {token}"}


def _trace(client_trace_id: str, status: str, now: datetime) -> dict:
    t0 = now
    t1 = now + timedelta(milliseconds=1200)
    s0 = now + timedelta(milliseconds=20)
    s1 = now + timedelta(milliseconds=1100)
    return {
        "client_trace_id": client_trace_id,
        "name": "docops.summarize",
        "service": "docops-api",
        "environment": "prod",
        "started_at": t0.isoformat(),
        "ended_at": t1.isoformat(),
        "status": status,
        "tags": {"feature": "summarization"},
        "metadata": {},
        "spans": [
            {
                "client_span_id": f"cs_{client_trace_id}",
                "type": "llm_call",
                "name": "openai.chat.completions",
                "started_at": s0.isoformat(),
                "ended_at": s1.isoformat(),
                "status": "ok" if status == "ok" else "error",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "tokens_in": 300,
                "tokens_out": 120,
                "messages_in": [{"role": "user", "content": "Summarize"}],
                "messages_out": [{"role": "assistant", "content": "Summary"}],
                "events": [],
            }
        ],
    }


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_analytics_overview_returns_kpis_and_series() -> None:
    client = TestClient(app)
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="User One"))
        db.commit()
    headers = _auth_header("usr_1", "u1@example.com", "User One")
    org = client.post("/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"}).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={"organization_id": org["id"], "name": "DocOps", "slug": "docops"},
    ).json()
    key = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()["key"]

    now = datetime.now(timezone.utc)
    payload = {"traces": [_trace("ct_ok", "ok", now), _trace("ct_err", "error", now + timedelta(seconds=1))]}
    ing = client.post("/v1/traces", headers={"X-EvalOps-Key": key}, json=payload)
    assert ing.status_code == 202
    assert ing.json()["ingested"] == 2

    overview = client.get(f"/v1/analytics/overview?project_id={project['id']}", headers=headers)
    assert overview.status_code == 200
    body = overview.json()
    assert body["kpis"]["traces"] == 2
    assert body["kpis"]["latency_p95_ms"] > 0
    assert body["kpis"]["cost_usd"] > 0
    assert body["kpis"]["error_rate"] == 0.5
    assert len(body["cost_by_day"]) >= 1
    assert len(body["model_breakdown"]) == 1
    assert len(body["recent_flagged"]) >= 1


def _bootstrap_project_with_two_traces(client: TestClient) -> tuple[dict[str, str], str, list[str]]:
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="User One"))
        db.commit()
    headers = _auth_header("usr_1", "u1@example.com", "User One")
    org = client.post("/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"}).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={"organization_id": org["id"], "name": "DocOps", "slug": "docops"},
    ).json()
    key = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()["key"]

    now = datetime.now(timezone.utc)
    payload = {"traces": [_trace("ct_fresh", "ok", now), _trace("ct_stale", "error", now)]}
    ing = client.post("/v1/traces", headers={"X-EvalOps-Key": key}, json=payload)
    assert ing.status_code == 202
    with SessionLocal() as db:
        rows = (
            db.query(Trace)
            .filter(Trace.project_id == project["id"])
            .order_by(Trace.created_at.asc())
            .all()
        )
        trace_ids = {row.client_trace_id: row.id for row in rows}
    assert "ct_fresh" in trace_ids and "ct_stale" in trace_ids
    return headers, project["id"], [trace_ids["ct_fresh"], trace_ids["ct_stale"]]


def test_analytics_overview_window_24h_excludes_older_trace() -> None:
    client = TestClient(app)
    headers, project_id, trace_ids = _bootstrap_project_with_two_traces(client)

    # Backdate the second trace to 48h ago. With window=24h it must drop out
    # of KPIs, cost_by_day, model_breakdown and recent_flagged.
    backdated = datetime.now(timezone.utc) - timedelta(hours=48)
    with SessionLocal() as db:
        stale = db.get(Trace, trace_ids[1])
        assert stale is not None
        stale.created_at = backdated
        db.add(stale)
        db.commit()

    qs_24h = f"/v1/analytics/overview?project_id={project_id}&window=24h"
    body_24h = client.get(qs_24h, headers=headers).json()
    assert body_24h["kpis"]["traces"] == 1
    # The stale (error) trace must not pull error_rate up to 0.5.
    assert body_24h["kpis"]["error_rate"] == 0.0
    assert all("ct_stale" not in str(row) for row in body_24h["recent_flagged"])

    qs_7d = f"/v1/analytics/overview?project_id={project_id}&window=7d"
    body_7d = client.get(qs_7d, headers=headers).json()
    assert body_7d["kpis"]["traces"] == 2
    assert body_7d["kpis"]["error_rate"] == 0.5


def test_analytics_overview_window_rejects_invalid_value() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap_project_with_two_traces(client)
    bad = client.get(f"/v1/analytics/overview?project_id={project_id}&window=90d", headers=headers)
    assert bad.status_code == 422
