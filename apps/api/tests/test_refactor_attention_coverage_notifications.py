from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import EvaluationRun, Notification, Rubric, User
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


def _trace_payload(client_trace_id: str, status: str, now: datetime) -> dict:
    return {
        "client_trace_id": client_trace_id,
        "name": "rag.answer.compose",
        "service": "aurora-rag",
        "environment": "prod",
        "started_at": now.isoformat(),
        "ended_at": (now + timedelta(milliseconds=700)).isoformat(),
        "status": status,
        "tags": {},
        "metadata": {},
        "spans": [
            {
                "client_span_id": f"sp_{client_trace_id}",
                "type": "llm_call",
                "name": "openai.chat",
                "started_at": (now + timedelta(milliseconds=50)).isoformat(),
                "ended_at": (now + timedelta(milliseconds=650)).isoformat(),
                "status": "ok" if status == "ok" else "error",
                "provider": "openai",
                "model": "gpt-4o-mini",
                "tokens_in": 20,
                "tokens_out": 10,
                "error": {"type": "schema_mismatch"} if status != "ok" else None,
                "events": [
                    {
                        "type": "llm.completion",
                        "occurred_at": (now + timedelta(milliseconds=640)).isoformat(),
                        "payload": {"ok": status == "ok"},
                    }
                ],
            }
        ],
    }


def _ingest_two_traces(client: TestClient, api_key: str) -> list[str]:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            _trace_payload("ct_ok", "ok", now),
            _trace_payload("ct_err", "error", now + timedelta(seconds=1)),
        ]
    }
    response = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert response.status_code == 202, response.text
    return [item["trace_id"] for item in response.json()["results"]]


def test_attention_and_sdk_status_endpoints() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    _ingest_two_traces(client, api_key)

    attention = client.get(f"/v1/projects/{project_id}/attention", headers=headers)
    assert attention.status_code == 200
    body = attention.json()
    assert body["count"] == 1
    assert body["items"][0]["cause"] == "schema_mismatch"
    assert body["items"][0]["service"] == "aurora-rag"

    sdk = client.get(f"/v1/projects/{project_id}/sdk-status", headers=headers)
    assert sdk.status_code == 200
    sdk_body = sdk.json()
    assert sdk_body["spans_per_minute"] > 0
    assert sdk_body["last_event_at"] is not None
    assert sdk_body["services_seen"] == ["aurora-rag"]


def test_coverage_endpoint_reports_completed_eval_runs() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    trace_ids = _ingest_two_traces(client, api_key)

    with SessionLocal() as db:
        rubric = Rubric(
            id="rb_coverage",
            project_id=project_id,
            slug="answer-grounding",
            description=None,
            current_version=1,
            threshold=0.7,
        )
        db.add(rubric)
        db.add(
            EvaluationRun(
                id="evr_coverage",
                project_id=project_id,
                trace_id=trace_ids[0],
                rubric_id=rubric.id,
                rubric_version=1,
                triggered_by="test",
                status="completed",
                aggregate_score=0.9,
                passed=True,
                cost_usd=0,
                run_metadata={},
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    response = client.get(f"/v1/projects/{project_id}/coverage", headers=headers)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["rubric_slug"] == "answer-grounding"
    assert data[0]["coverage"] == 0.5
    assert data[0]["runs_7d"] == 1


def test_notifications_list_and_mark_read() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)

    with SessionLocal() as db:
        db.add(
            Notification(
                id="ntf_1",
                project_id=project_id,
                kind="warn",
                title="Trace com schema_mismatch",
                meta={"trace_id": "tr_1"},
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    listed = client.get(f"/v1/projects/{project_id}/notifications", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["unread_count"] == 1
    assert listed.json()["data"][0]["title"] == "Trace com schema_mismatch"

    marked = client.post(
        f"/v1/projects/{project_id}/notifications/mark-read",
        headers=headers,
        json={"ids": ["ntf_1"]},
    )
    assert marked.status_code == 200
    assert marked.json()["updated"] == 1

    listed_again = client.get(f"/v1/projects/{project_id}/notifications", headers=headers)
    assert listed_again.json()["unread_count"] == 0
    assert listed_again.json()["data"][0]["read_at"] is not None
