from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import create_access_token


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _auth_header(user_id: str = "usr_1") -> dict[str, str]:
    token = create_access_token(sub=user_id, email="u1@example.com", name="User One")
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> tuple[dict[str, str], str, str]:
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="User One"))
        db.commit()
    headers = _auth_header()
    org = client.post(
        "/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"}
    ).json()
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


def _ingest_trace(client: TestClient, api_key: str, status: str = "ok") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": f"ct_{status}",
                "name": "rag.answer.compose",
                "service": "aurora-rag",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=500)).isoformat(),
                "status": status,
                "tags": {},
                "metadata": {},
                "spans": [
                    {
                        "client_span_id": f"sp_{status}",
                        "type": "llm_call",
                        "name": "openai.chat",
                        "started_at": now.isoformat(),
                        "ended_at": (now + timedelta(milliseconds=400)).isoformat(),
                        "status": "ok" if status == "ok" else "error",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "tokens_in": 10,
                        "tokens_out": 5,
                        "error": None if status == "ok" else {"type": "schema_mismatch"},
                        "events": [],
                    }
                ],
            }
        ]
    }
    response = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert response.status_code == 202, response.text
    return response.json()["results"][0]["trace_id"]


def test_attention_empty_project_returns_no_items() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    response = client.get(f"/v1/projects/{project_id}/attention", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["items"] == []


def test_coverage_empty_when_no_rubrics() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    response = client.get(f"/v1/projects/{project_id}/coverage", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_sdk_status_zero_when_no_ingestion() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    response = client.get(f"/v1/projects/{project_id}/sdk-status", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["spans_per_minute"] == 0
    assert body["last_event_at"] is None
    assert body["services_seen"] == []


def test_notifications_mark_read_idempotent() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    first = client.post(
        f"/v1/projects/{project_id}/notifications/mark-read",
        headers=headers,
        json={"ids": ["ntf_missing"]},
    )
    assert first.status_code == 200
    assert first.json()["updated"] == 0


def test_attention_requires_auth() -> None:
    client = TestClient(app)
    _, project_id, _ = _bootstrap(client)
    response = client.get(f"/v1/projects/{project_id}/attention")
    assert response.status_code == 401


def test_flag_trace_rejects_unknown_trace() -> None:
    client = TestClient(app)
    headers, _, _ = _bootstrap(client)
    response = client.post(
        "/v1/traces/tr_nope/flags",
        headers=headers,
        json={"reason": "manual", "note": "bug"},
    )
    assert response.status_code == 404


def test_rerun_trace_rejects_unknown_trace() -> None:
    client = TestClient(app)
    headers, _, _ = _bootstrap(client)
    response = client.post(
        "/v1/traces/tr_nope/rerun",
        headers=headers,
        json={"reason": "investigate"},
    )
    assert response.status_code == 404


def test_compare_same_trace_returns_zero_deltas() -> None:
    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")
    response = client.post(
        "/v1/traces/compare",
        headers=headers,
        json={"left_trace_id": trace_id, "right_trace_id": trace_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["left"]["id"] == trace_id
    assert body["right"]["id"] == trace_id
    assert "diff" in body


def test_rag_endpoint_returns_empty_when_no_rag_spans() -> None:
    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")
    response = client.get(f"/v1/traces/{trace_id}/rag", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert body["claims"] == []


def test_evaluation_summary_zero_when_no_runs() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    response = client.get(
        f"/v1/projects/{project_id}/evaluations/summary", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["active_rubrics"] == 0
    assert body["runs_7d"] == 0


def test_exports_listing_empty_when_no_jobs() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    response = client.get(f"/v1/projects/{project_id}/exports", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def test_prompt_usage_rejects_unknown_prompt() -> None:
    client = TestClient(app)
    headers, _, _ = _bootstrap(client)
    response = client.get("/v1/prompts/pr_nope/usage", headers=headers)
    assert response.status_code == 404


def test_patch_project_rejects_unknown_project() -> None:
    client = TestClient(app)
    headers, _, _ = _bootstrap(client)
    response = client.patch(
        "/v1/projects/proj_nope",
        headers=headers,
        json={"environment": "staging"},
    )
    assert response.status_code == 404


def test_members_rejects_unknown_org() -> None:
    client = TestClient(app)
    headers, _, _ = _bootstrap(client)
    response = client.get("/v1/organizations/org_nope/members", headers=headers)
    assert response.status_code == 404


def test_bulk_flag_traces_creates_one_per_id() -> None:
    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="error")
    response = client.post(
        "/v1/traces/bulk-flag",
        headers=headers,
        json={"trace_ids": [trace_id], "reason": "schema_mismatch", "note": "bulk"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 1
    assert body["data"][0]["trace_id"] == trace_id
