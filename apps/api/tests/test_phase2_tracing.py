from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Trace, User
from app.security import create_access_token


def _auth_header(user_id: str, email: str, name: str) -> dict[str, str]:
    token = create_access_token(sub=user_id, email=email, name=name)
    return {"Authorization": f"Bearer {token}"}


def _bootstrap_project_and_key(client: TestClient) -> tuple[dict[str, str], str, str]:
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
    return headers, project["id"], key


def _trace_payload(client_trace_id: str, now: datetime | None = None) -> dict:
    t0 = now or datetime.now(timezone.utc)
    t1 = t0 + timedelta(milliseconds=1200)
    s0 = t0 + timedelta(milliseconds=50)
    s1 = t0 + timedelta(milliseconds=1150)
    return {
        "traces": [
            {
                "client_trace_id": client_trace_id,
                "name": "docops.summarize",
                "service": "docops-agent",
                "environment": "prod",
                "started_at": t0.isoformat(),
                "ended_at": t1.isoformat(),
                "status": "ok",
                "tags": {"feature": "summarization"},
                "user_ref": "u_anon_a1",
                "metadata": {"trace_type": "agent_response"},
                "spans": [
                    {
                        "client_span_id": "cs_root",
                        "type": "llm_call",
                        "name": "openai.chat.completions",
                        "started_at": s0.isoformat(),
                        "ended_at": s1.isoformat(),
                        "status": "ok",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "tokens_in": 200,
                        "tokens_out": 100,
                        "messages_in": [{"role": "user", "content": "Summarize this policy"}],
                        "messages_out": [{"role": "assistant", "content": "Summary"}],
                        "events": [
                            {
                                "type": "cache_miss",
                                "occurred_at": (s0 + timedelta(milliseconds=100)).isoformat(),
                                "payload": {"layer": "prompt-cache"},
                            }
                        ],
                    }
                ],
            }
        ]
    }


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_trace_ingestion_happy_path_and_idempotency() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap_project_and_key(client)

    payload = _trace_payload("ct_1")
    ingest = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert ingest.status_code == 202
    body = ingest.json()
    assert body["ingested"] == 1
    assert body["errors"] == []
    trace_id = body["results"][0]["trace_id"]

    second = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert second.status_code == 202
    assert second.json()["results"][0]["trace_id"] == trace_id

    with SessionLocal() as db:
        rows = db.query(Trace).filter(Trace.project_id == project_id).all()
        assert len(rows) == 1
        assert rows[0].total_tokens_in == 200
        assert rows[0].total_tokens_out == 100
        assert float(rows[0].total_cost_usd) > 0

    listed = client.get(f"/v1/traces?project_id={project_id}", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == trace_id

    detail = client.get(f"/v1/traces/{trace_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["events_count"] == 1


def test_trace_ingestion_partial_error_batch() -> None:
    client = TestClient(app)
    _, _, api_key = _bootstrap_project_and_key(client)
    now = datetime.now(timezone.utc)
    good = _trace_payload("ct_good", now=now)["traces"][0]
    bad = _trace_payload("ct_bad", now=now)["traces"][0]
    bad["ended_at"] = (now - timedelta(seconds=1)).isoformat()
    payload = {"traces": [good, bad]}

    ingest = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert ingest.status_code == 202
    body = ingest.json()
    assert body["ingested"] == 1
    assert len(body["errors"]) == 1
    assert body["errors"][0]["client_trace_id"] == "ct_bad"
