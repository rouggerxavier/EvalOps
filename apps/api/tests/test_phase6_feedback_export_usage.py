from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Plan, Subscription, User
from app.security import create_access_token, new_id

client = TestClient(app)


def _auth_header(user_id: str, email: str, name: str) -> dict[str, str]:
    token = create_access_token(sub=user_id, email=email, name=name)
    return {"Authorization": f"Bearer {token}"}


def _bootstrap() -> tuple[dict[str, str], str, str]:
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
    return headers, org["id"], project["id"]


def _create_api_key(headers: dict[str, str], project_id: str) -> str:
    return client.post(
        f"/v1/projects/{project_id}/api-keys",
        headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()["key"]


def _ingest_trace(api_key: str, *, name: str = "trace", environment: str = "prod", status: str = "ok") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": f"ct_{name}",
                "name": name,
                "service": "docops-agent",
                "environment": environment,
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=1000)).isoformat(),
                "status": status,
                "tags": {"feature": "summarization"},
                "metadata": {"trace_type": "agent_response"},
                "spans": [
                    {
                        "client_span_id": "cs_root",
                        "type": "llm_call",
                        "name": "openai.chat.completions",
                        "started_at": (now + timedelta(milliseconds=50)).isoformat(),
                        "ended_at": (now + timedelta(milliseconds=900)).isoformat(),
                        "status": "ok",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "tokens_in": 100,
                        "tokens_out": 50,
                        "messages_in": [{"role": "user", "content": "Oi"}],
                        "messages_out": [{"role": "assistant", "content": "Ola"}],
                    }
                ],
            }
        ]
    }
    resp = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert resp.status_code == 202
    return resp.json()["results"][0]["trace_id"]


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_feedback_create_validation_and_list() -> None:
    headers, _, project_id = _bootstrap()
    api_key = _create_api_key(headers, project_id)
    trace_id = _ingest_trace(api_key, name="feedback-trace")

    bad = client.post(
        f"/v1/traces/{trace_id}/feedback",
        headers=headers,
        json={"source": "dashboard"},
    )
    assert bad.status_code == 422

    created = client.post(
        f"/v1/traces/{trace_id}/feedback",
        headers=headers,
        json={"source": "dashboard", "thumbs": "down", "comment": "resposta incompleta"},
    )
    assert created.status_code == 201
    assert created.json()["feedback"]["thumbs"] == "down"

    listed = client.get(f"/v1/traces/{trace_id}/feedback", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 1

    detail = client.get(f"/v1/traces/{trace_id}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["feedback"]) == 1


def test_export_jsonl_valid_and_filters_subset() -> None:
    headers, _, project_id = _bootstrap()
    api_key = _create_api_key(headers, project_id)
    _ingest_trace(api_key, name="prod-ok", environment="prod", status="ok")
    _ingest_trace(api_key, name="dev-error", environment="dev", status="error")

    created = client.post(
        "/v1/exports",
        headers=headers,
        json={"project_id": project_id, "format": "jsonl", "filters": {"environment": "prod"}},
    )
    assert created.status_code == 202
    export_id = created.json()["export_id"]

    job = client.get(f"/v1/exports/{export_id}", headers=headers)
    assert job.status_code == 200
    assert job.json()["status"] == "completed"
    assert job.json()["row_count"] == 1
    file_path = Path(job.json()["file_path"])
    assert file_path.exists()

    lines = file_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "\"environment\": \"prod\"" in lines[0]


def test_usage_increments_and_quota_exceeded() -> None:
    headers, org_id, project_id = _bootstrap()
    with SessionLocal() as db:
        plan = Plan(
            id=new_id("pln"),
            code="tiny",
            name="Tiny",
            monthly_trace_limit=1,
            monthly_eval_limit=1,
            monthly_export_limit=1,
        )
        db.add(plan)
        db.flush()
        db.add(
            Subscription(
                id=new_id("sub"),
                organization_id=org_id,
                plan_id=plan.id,
                status="active",
            )
        )
        db.commit()

    api_key = _create_api_key(headers, project_id)
    _ingest_trace(api_key, name="first")

    second = client.post(
        "/v1/traces",
        headers={"X-EvalOps-Key": api_key},
        json={
            "traces": [
                {
                    "client_trace_id": "ct_second",
                    "name": "second",
                    "service": "svc",
                    "environment": "prod",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "ended_at": (datetime.now(timezone.utc) + timedelta(milliseconds=10)).isoformat(),
                    "status": "ok",
                    "spans": [],
                }
            ]
        },
    )
    assert second.status_code == 402
    # Phase 6 (G-07) extended the quota detail to a structured payload so the
    # client can distinguish which monthly limit was hit.
    detail = second.json()["detail"]
    assert detail["error"] == "quota_exceeded"
    assert detail["field"] == "traces_ingested"

    usage = client.get(f"/v1/organizations/{org_id}/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["traces_ingested"] == 1
