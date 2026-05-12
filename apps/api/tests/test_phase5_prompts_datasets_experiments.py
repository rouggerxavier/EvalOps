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


def _ingest_trace(api_key: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": "ct_phase5",
                "name": "docops.summarize",
                "service": "docops-agent",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=1200)).isoformat(),
                "status": "ok",
                "tags": {"feature": "summarization"},
                "metadata": {"trace_type": "agent_response"},
                "spans": [
                    {
                        "client_span_id": "cs_root",
                        "type": "llm_call",
                        "name": "openai.chat.completions",
                        "started_at": (now + timedelta(milliseconds=50)).isoformat(),
                        "ended_at": (now + timedelta(milliseconds=1100)).isoformat(),
                        "status": "ok",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "tokens_in": 200,
                        "tokens_out": 100,
                        "messages_in": [{"role": "user", "content": "Summarize this policy"}],
                        "messages_out": [{"role": "assistant", "content": "Summary"}],
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


def test_prompt_versioning_is_immutable() -> None:
    headers, _, project_id = _bootstrap()
    created = client.post(
        f"/v1/projects/{project_id}/prompts",
        headers=headers,
        json={
            "slug": "support-answer-system",
            "description": "Support prompt",
            "template": "You are helpful. User: {{ user_message }}",
            "variables": {"user_message": {"type": "string", "required": True}},
            "metadata": {"model_default": "openai/gpt-4o-mini"},
            "changelog": "Initial",
        },
    )
    assert created.status_code == 201
    prompt_id = created.json()["prompt"]["id"]
    assert created.json()["version"]["version"] == 1

    v2 = client.post(
        f"/v1/prompts/{prompt_id}/versions",
        headers=headers,
        json={
            "template": "You are very helpful. User: {{ user_message }}",
            "variables": {"user_message": {"type": "string", "required": True}},
            "metadata": {"model_default": "openai/gpt-4.1"},
            "changelog": "Refined wording",
        },
    )
    assert v2.status_code == 201
    assert v2.json()["prompt_version"] == 2

    versions = client.get(f"/v1/prompts/{prompt_id}/versions", headers=headers)
    assert versions.status_code == 200
    data = versions.json()["data"]
    assert len(data) == 2
    assert data[0]["version"] == 1
    assert data[1]["version"] == 2
    assert data[0]["template"] == "You are helpful. User: {{ user_message }}"
    assert data[1]["template"] == "You are very helpful. User: {{ user_message }}"


def test_dataset_item_create_and_list() -> None:
    headers, _, project_id = _bootstrap()
    dataset = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"slug": "golden-support", "description": "Golden set", "source": "manual"},
    )
    assert dataset.status_code == 201
    dataset_id = dataset.json()["id"]

    add_items = client.post(
        f"/v1/datasets/{dataset_id}/items",
        headers=headers,
        json={
            "items": [
                {
                    "input": {"messages": [{"role": "user", "content": "Oi"}]},
                    "expected_output": {"assistant_message": "Ola!"},
                    "metadata": {"source": "manual"},
                },
                {
                    "input": {"messages": [{"role": "user", "content": "Preciso de ajuda"}]},
                    "expected_output": {"assistant_message": "Claro, como posso ajudar?"},
                    "metadata": {"source": "manual"},
                },
            ]
        },
    )
    assert add_items.status_code == 201
    assert add_items.json()["created"] == 2

    listed = client.get(f"/v1/datasets/{dataset_id}/items", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["data"]) == 2


def test_experiment_with_two_variants_runs_and_returns_summary() -> None:
    headers, _, project_id = _bootstrap()
    api_key = _create_api_key(headers, project_id)
    _ingest_trace(api_key)

    rubric_yaml = """
slug: support-quality
name: Support Quality
description: Minimal rubric
threshold: 0.5
aggregate: weighted_mean
evaluators:
  - id: length_check
    type: length_bounds
    weight: 1.0
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 5
      max: 500
"""
    rubric = client.post(
        f"/v1/projects/{project_id}/rubrics",
        headers=headers,
        json={"yaml_source": rubric_yaml},
    )
    assert rubric.status_code == 201
    rubric_id = rubric.json()["rubric"]["id"]

    dataset = client.post(
        f"/v1/projects/{project_id}/datasets",
        headers=headers,
        json={"slug": "trace-replay", "description": "Replay traces", "source": "traces"},
    )
    assert dataset.status_code == 201
    dataset_id = dataset.json()["id"]

    built = client.post(
        f"/v1/datasets/{dataset_id}/build-from-traces",
        headers=headers,
        json={"environment": "prod", "limit": 10},
    )
    assert built.status_code == 202
    assert built.json()["created"] >= 1

    experiment = client.post(
        f"/v1/projects/{project_id}/experiments",
        headers=headers,
        json={
            "name": "model-comparison",
            "dataset_id": dataset_id,
            "rubric_id": rubric_id,
            "variants": [
                {"name": "control", "model": "openai/gpt-4o-mini", "params": {"temperature": 0.2}},
                {"name": "candidate", "model": "openai/gpt-4.1", "params": {"temperature": 0.2}},
            ],
            "baseline_variant": "control",
            "pass_criteria": {"min_pass_rate": 0.5, "no_regression_vs": "control"},
        },
    )
    assert experiment.status_code == 201
    experiment_id = experiment.json()["id"]

    run = client.post(f"/v1/experiments/{experiment_id}/run", headers=headers, json={"triggered_by": "api"})
    assert run.status_code == 202
    run_id = run.json()["run_id"]
    assert run.json()["status"] in ["completed", "error"]

    detail = client.get(f"/v1/experiments/{experiment_id}/runs/{run_id}", headers=headers)
    assert detail.status_code == 200
    run_data = detail.json()["run"]
    assert "by_variant" in run_data
    assert "control" in run_data["by_variant"]
    assert "candidate" in run_data["by_variant"]
