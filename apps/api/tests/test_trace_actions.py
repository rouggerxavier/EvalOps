from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Trace, TraceFlag, User
from app.security import create_access_token


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _auth_header(user_id: str = "usr_1") -> dict[str, str]:
    token = create_access_token(sub=user_id, email="u1@example.com", name="User One")
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> tuple[dict[str, str], str]:
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
    return headers, key


def _trace_payload(
    client_trace_id: str,
    status: str,
    now: datetime,
    duration_ms: int,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
) -> dict:
    span_status = "error" if status == "error" else "ok"
    return {
        "client_trace_id": client_trace_id,
        "name": "rag.answer.compose",
        "service": "aurora-rag",
        "environment": "prod",
        "started_at": now.isoformat(),
        "ended_at": (now + timedelta(milliseconds=duration_ms)).isoformat(),
        "status": status,
        "tags": {"tenant": "demo"},
        "metadata": {"case": client_trace_id},
        "spans": [
            {
                "client_span_id": f"sp_{client_trace_id}",
                "type": "llm_call",
                "name": "openai.chat",
                "started_at": (now + timedelta(milliseconds=25)).isoformat(),
                "ended_at": (now + timedelta(milliseconds=duration_ms - 25)).isoformat(),
                "status": span_status,
                "provider": "openai",
                "model": "gpt-4o-mini",
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "error": {"type": "schema_mismatch"} if status == "error" else None,
            }
        ],
    }


def _ingest_two_traces(client: TestClient, api_key: str) -> list[str]:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            _trace_payload("ct_ok", "ok", now, 500, 20, 10, 0.01),
            _trace_payload("ct_err", "error", now + timedelta(seconds=3), 900, 40, 20, 0.05),
        ]
    }
    response = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert response.status_code == 202, response.text
    return [item["trace_id"] for item in response.json()["results"]]


def test_flag_trace_and_bulk_flag_create_rows() -> None:
    client = TestClient(app)
    headers, api_key = _bootstrap(client)
    trace_ids = _ingest_two_traces(client, api_key)

    single = client.post(
        f"/v1/traces/{trace_ids[0]}/flags",
        headers=headers,
        json={"reason": "low_quality", "note": "Needs review"},
    )
    assert single.status_code == 201, single.text
    assert single.json()["trace_id"] == trace_ids[0]
    assert single.json()["reason"] == "low_quality"

    bulk = client.post(
        "/v1/traces/bulk-flag",
        headers=headers,
        json={"trace_ids": trace_ids, "reason": "schema_mismatch", "note": "Bulk triage"},
    )
    assert bulk.status_code == 201, bulk.text
    assert bulk.json()["created"] == 2

    with SessionLocal() as db:
        rows = db.query(TraceFlag).order_by(TraceFlag.created_at.asc()).all()
        assert len(rows) == 3
        assert {row.reason for row in rows} == {"low_quality", "schema_mismatch"}


def test_rerun_trace_creates_queued_replay_trace() -> None:
    client = TestClient(app)
    headers, api_key = _bootstrap(client)
    trace_id = _ingest_two_traces(client, api_key)[0]

    response = client.post(
        f"/v1/traces/{trace_id}/rerun",
        headers=headers,
        json={"model": "gpt-4.1-mini", "variables": {"question": "retry"}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["new_trace_id"] != trace_id

    with SessionLocal() as db:
        replay = db.get(Trace, body["new_trace_id"])
        assert replay is not None
        assert replay.status == "partial"
        assert replay.metadata_json["replay_of"] == trace_id
        assert replay.metadata_json["replay_status"] == "queued"
        assert replay.metadata_json["rerun_model"] == "gpt-4.1-mini"


def test_compare_traces_reports_status_cost_token_and_span_deltas() -> None:
    client = TestClient(app)
    headers, api_key = _bootstrap(client)
    left_id, right_id = _ingest_two_traces(client, api_key)

    response = client.post(
        "/v1/traces/compare",
        headers=headers,
        json={"left_trace_id": left_id, "right_trace_id": right_id},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["left"]["id"] == left_id
    assert body["right"]["id"] == right_id
    assert body["diff"]["status_changed"] is True
    assert body["diff"]["duration_delta_ms"] == 400
    assert body["diff"]["token_delta"] == 30
    assert round(body["diff"]["cost_delta_usd"], 2) == 0.04
    assert body["diff"]["spans"][0]["name"] == "openai.chat"
    assert body["diff"]["spans"][0]["error_delta"] == 1
