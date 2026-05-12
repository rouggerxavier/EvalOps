from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import create_access_token

client = TestClient(app)


def _auth_header(user_id: str, email: str, name: str) -> dict[str, str]:
    token = create_access_token(sub=user_id, email=email, name=name)
    return {"Authorization": f"Bearer {token}"}


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_e2e_happy_path_mvp_flow() -> None:
    with SessionLocal() as db:
        db.add(User(id="usr_e2e", email="e2e@example.com", name="E2E User"))
        db.commit()
    headers = _auth_header("usr_e2e", "e2e@example.com", "E2E User")

    # 1) identity + tenancy
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

    # 2) tracing ingestion + read path
    now = datetime.now(timezone.utc)
    ingest = client.post(
        "/v1/traces",
        headers={"X-EvalOps-Key": key},
        json={
            "traces": [
                {
                    "client_trace_id": "ct_e2e_1",
                    "name": "chat.answer",
                    "service": "docops-api",
                    "environment": "prod",
                    "started_at": now.isoformat(),
                    "ended_at": (now + timedelta(milliseconds=1200)).isoformat(),
                    "status": "ok",
                    "tags": {"feature": "support"},
                    "metadata": {"source": "e2e"},
                    "spans": [
                        {
                            "client_span_id": "cs_root",
                            "type": "llm_call",
                            "name": "openai.chat.completions",
                            "started_at": (now + timedelta(milliseconds=20)).isoformat(),
                            "ended_at": (now + timedelta(milliseconds=1100)).isoformat(),
                            "status": "ok",
                            "provider": "openai",
                            "model": "gpt-4o-mini",
                            "tokens_in": 120,
                            "tokens_out": 80,
                            "messages_in": [{"role": "user", "content": "oi"}],
                            "messages_out": [{"role": "assistant", "content": "ola"}],
                        }
                    ],
                }
            ]
        },
    )
    assert ingest.status_code == 202
    trace_id = ingest.json()["results"][0]["trace_id"]

    traces = client.get(f"/v1/traces?project_id={project['id']}", headers=headers)
    assert traces.status_code == 200
    assert len(traces.json()["data"]) == 1

    detail = client.get(f"/v1/traces/{trace_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["trace"]["id"] == trace_id

    # 3) rubric + evaluation
    rubric_yaml = """
slug: support-quality
name: Support Quality
description: Minimal rubric
threshold: 0.5
aggregate: weighted_mean
evaluators:
  - id: length_check
    type: length_bounds
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 2
      max: 500
"""
    rubric = client.post(
        f"/v1/projects/{project['id']}/rubrics",
        headers=headers,
        json={"yaml_source": rubric_yaml},
    )
    assert rubric.status_code == 201
    rubric_id = rubric.json()["rubric"]["id"]

    eval_run = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "api"},
    )
    assert eval_run.status_code == 201

    # 4) feedback + export + usage
    feedback = client.post(
        f"/v1/traces/{trace_id}/feedback",
        headers=headers,
        json={"source": "dashboard", "thumbs": "up", "comment": "boa resposta"},
    )
    assert feedback.status_code == 201

    export = client.post(
        "/v1/exports",
        headers=headers,
        json={"project_id": project["id"], "format": "jsonl", "filters": {"environment": "prod"}},
    )
    assert export.status_code == 202

    usage = client.get(f"/v1/organizations/{org['id']}/usage", headers=headers)
    assert usage.status_code == 200
    body = usage.json()
    assert body["traces_ingested"] >= 1
    assert body["evaluations_run"] >= 1
    assert body["exports_created"] >= 1

    # 5) docs + health
    assert client.get("/health/liveness").status_code == 200
    assert client.get("/health/readiness").status_code == 200
    assert client.get("/docs").status_code == 200
