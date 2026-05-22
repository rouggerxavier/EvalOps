from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import EvaluationRun, ExportJob, Rubric, Trace, User
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


def _ingest_rag_trace(client: TestClient, api_key: str, prompt_ref: str = "support-bot@1") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": "rag-1",
                "name": "rag.answer.compose",
                "service": "support-rag",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=900)).isoformat(),
                "status": "ok",
                "tags": {"kind": "rag"},
                "metadata": {"pipeline_version": "2026.05"},
                "spans": [
                    {
                        "client_span_id": "retrieve",
                        "type": "retrieval",
                        "name": "rag.retrieve",
                        "started_at": (now + timedelta(milliseconds=10)).isoformat(),
                        "ended_at": (now + timedelta(milliseconds=210)).isoformat(),
                        "status": "ok",
                        "prompt_version_ref": prompt_ref,
                        "output": {
                            "retrieved_count": 2,
                            "citations": [
                                {
                                    "title": "Refund policy",
                                    "score": 0.92,
                                    "source": "docs/refunds",
                                    "chunk": "refund-01",
                                },
                                {
                                    "title": "SLA",
                                    "score": 0.76,
                                    "source": "docs/sla",
                                    "chunk": "sla-02",
                                },
                            ],
                        },
                    },
                    {
                        "client_span_id": "grounding",
                        "type": "eval",
                        "name": "rag.grounding.validate",
                        "started_at": (now + timedelta(milliseconds=220)).isoformat(),
                        "ended_at": (now + timedelta(milliseconds=420)).isoformat(),
                        "status": "ok",
                        "output": {
                            "quality_score": 0.84,
                            "claims": [
                                {"text": "Refunds take five days", "grounded": True, "cite": "refund-01"},
                                {"text": "Premium has phone support", "grounded": False},
                            ],
                            "claim_to_chunk": [
                                {"claim": "Refunds take five days", "chunk": "refund-01", "score": 0.9}
                            ],
                        },
                    },
                    {
                        "client_span_id": "finalize",
                        "type": "llm_call",
                        "name": "response.finalize",
                        "started_at": (now + timedelta(milliseconds=430)).isoformat(),
                        "ended_at": (now + timedelta(milliseconds=860)).isoformat(),
                        "status": "ok",
                        "output": {"answer_preview": "Refunds are usually processed within five days."},
                    },
                ],
            }
        ]
    }
    response = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert response.status_code == 202, response.text
    return response.json()["results"][0]["trace_id"]


def test_rag_consolidated_endpoint_returns_claim_level_summary() -> None:
    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_rag_trace(client, api_key)

    response = client.get(f"/v1/traces/{trace_id}/rag", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["retrieved_docs"] == 2
    assert body["grounded_claims"] == 1
    assert body["ungrounded_claims"] == 1
    assert body["hallucination_risk"] == "medium"
    assert body["answer_preview"].startswith("Refunds are")
    assert body["citations"][0]["chunk"] == "refund-01"
    assert body["claim_to_chunk"][0]["score"] == 0.9


def test_evaluation_summary_reports_active_runs_pass_rate_and_cost() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    trace_id = _ingest_rag_trace(client, api_key)

    with SessionLocal() as db:
        rubric = Rubric(
            id="rb_summary",
            project_id=project_id,
            slug="grounding",
            description=None,
            current_version=1,
            threshold=0.7,
        )
        db.add(rubric)
        db.add_all(
            [
                EvaluationRun(
                    id="evr_pass",
                    project_id=project_id,
                    trace_id=trace_id,
                    rubric_id=rubric.id,
                    rubric_version=1,
                    triggered_by="test",
                    status="completed",
                    aggregate_score=0.9,
                    passed=True,
                    cost_usd=0.02,
                    run_metadata={},
                    created_at=datetime.now(timezone.utc),
                ),
                EvaluationRun(
                    id="evr_fail",
                    project_id=project_id,
                    trace_id=trace_id,
                    rubric_id=rubric.id,
                    rubric_version=2,
                    triggered_by="test",
                    status="completed",
                    aggregate_score=0.4,
                    passed=False,
                    cost_usd=0.03,
                    run_metadata={},
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        db.commit()

    response = client.get(f"/v1/projects/{project_id}/evaluations/summary", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "active_rubrics": 1,
        "runs_7d": 2,
        "pass_rate": 0.5,
        "cost_usd": 0.05,
    }


def test_prompt_usage_lists_traces_referencing_prompt_versions() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    prompt = client.post(
        f"/v1/projects/{project_id}/prompts",
        headers=headers,
        json={
            "slug": "support-bot",
            "description": "Support answer prompt",
            "template": "Answer with citations",
            "variables": {},
            "metadata": {},
        },
    ).json()["prompt"]
    trace_id = _ingest_rag_trace(client, api_key, "support-bot@1")

    response = client.get(f"/v1/prompts/{prompt['id']}/usage", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["prompt_id"] == prompt["id"]
    assert body["usage_count"] == 1
    assert body["traces"][0]["trace_id"] == trace_id
    assert body["traces"][0]["prompt_version_ref"] == "support-bot@1"


def test_exports_listing_returns_project_jobs_descending() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        db.add_all(
            [
                ExportJob(
                    id="exp_old",
                    project_id=project_id,
                    status="completed",
                    format="jsonl",
                    filters={"status": "ok"},
                    row_count=3,
                    file_path="/tmp/old.jsonl",
                    created_by="usr_1",
                    created_at=now - timedelta(hours=1),
                ),
                ExportJob(
                    id="exp_new",
                    project_id=project_id,
                    status="pending",
                    format="jsonl",
                    filters={"status": "error"},
                    row_count=0,
                    created_by="usr_1",
                    created_at=now,
                ),
            ]
        )
        db.commit()

    response = client.get(f"/v1/projects/{project_id}/exports", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body["data"]] == ["exp_new", "exp_old"]
    assert body["next_cursor"] is None


def _ingest_trace_with_spans(
    client: TestClient,
    api_key: str,
    *,
    client_trace_id: str,
    trace_name: str,
    trace_duration_ms: int,
    spans: list[dict],
    metadata: dict | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": client_trace_id,
                "name": trace_name,
                "service": "svc",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=trace_duration_ms)).isoformat(),
                "status": "ok",
                "tags": {},
                "metadata": metadata or {},
                "spans": spans,
            }
        ]
    }
    response = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert response.status_code == 202, response.text
    return response.json()["results"][0]["trace_id"]


def _span(name: str, type_: str, start_ms: int, end_ms: int) -> dict:
    base = datetime.now(timezone.utc)
    return {
        "client_span_id": f"sp_{name.replace('.', '_')}_{start_ms}",
        "type": type_,
        "name": name,
        "started_at": (base + timedelta(milliseconds=start_ms)).isoformat(),
        "ended_at": (base + timedelta(milliseconds=end_ms)).isoformat(),
        "status": "ok",
    }


def test_slow_kind_llm_filters_traces_by_llm_span_duration() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)

    # Orchestrator trace: 5s total, only fast spans. Must NOT show up in slow=llm.
    orchestrator_id = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="orchestrator",
        trace_name="agent.run",
        trace_duration_ms=5000,
        spans=[
            _span("agent.plan", "tool", 0, 50),
            _span("agent.act", "tool", 60, 120),
        ],
    )
    # LLM trace: short total, but the llm_call span itself is slow.
    llm_id = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="slow-llm",
        trace_name="qa.compose",
        trace_duration_ms=3500,
        spans=[
            _span("openai.chat", "llm_call", 0, 3400),
        ],
    )

    response = client.get(
        f"/v1/traces?project_id={project_id}&slow_kind=llm&duration_gt=2000",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    ids = {row["id"] for row in body["data"]}
    assert llm_id in ids
    assert orchestrator_id not in ids
    item = next(row for row in body["data"] if row["id"] == llm_id)
    assert item["slow_reason"] == "llm"


def test_slow_kind_default_is_trace_duration() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)

    fast_id = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="fast",
        trace_name="qa.compose",
        trace_duration_ms=500,
        spans=[_span("openai.chat", "llm_call", 0, 480)],
    )
    slow_id = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="slow",
        trace_name="agent.run",
        trace_duration_ms=4000,
        spans=[_span("agent.act", "tool", 0, 3900)],
    )

    response = client.get(
        f"/v1/traces?project_id={project_id}&duration_gt=2000",
        headers=headers,
    )
    body = response.json()
    ids = {row["id"] for row in body["data"]}
    assert slow_id in ids and fast_id not in ids
    item = next(row for row in body["data"] if row["id"] == slow_id)
    assert item["slow_reason"] == "trace"


def test_rag_filter_matches_trace_with_only_response_finalize_span() -> None:
    """Bug 2.1: the detail page treats a `response.finalize` span as RAG even
    without `rag.%` spans. The list must keep the same contract."""
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)

    finalize_only = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="finalize-only",
        trace_name="qa.compose",
        trace_duration_ms=500,
        spans=[_span("response.finalize", "llm_call", 0, 480)],
    )
    plain = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="plain-llm",
        trace_name="qa.compose",
        trace_duration_ms=500,
        spans=[_span("openai.chat", "llm_call", 0, 480)],
    )

    body = client.get(f"/v1/traces?project_id={project_id}&rag=true", headers=headers).json()
    ids = {row["id"] for row in body["data"]}
    assert finalize_only in ids
    assert plain not in ids


def test_rag_filter_matches_trace_with_rag_metadata_keys() -> None:
    """Bug 2.1: metadata keys (pipeline_version, retrieved_count, …) declare a
    trace as RAG even when no span name matches."""
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)

    by_metadata = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="rag-by-metadata",
        trace_name="agent.run",
        trace_duration_ms=500,
        spans=[_span("openai.chat", "llm_call", 0, 480)],
        metadata={"pipeline_version": "2026.05", "retrieved_count": 3},
    )

    body = client.get(f"/v1/traces?project_id={project_id}&rag=true", headers=headers).json()
    ids = {row["id"] for row in body["data"]}
    assert by_metadata in ids


def test_rag_filter_matches_traces_via_span_name() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)

    # Non-RAG trace name but has a rag.retrieve span — must appear under rag=true.
    rag_id = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="rag-via-span",
        trace_name="agent.run",  # not rag.*
        trace_duration_ms=800,
        spans=[
            _span("rag.retrieve", "retrieval", 10, 200),
            _span("openai.chat", "llm_call", 210, 700),
        ],
    )
    # Plain agent trace — no RAG evidence — must NOT appear.
    plain_id = _ingest_trace_with_spans(
        client,
        api_key,
        client_trace_id="plain",
        trace_name="agent.run",
        trace_duration_ms=400,
        spans=[_span("openai.chat", "llm_call", 0, 380)],
    )

    response = client.get(f"/v1/traces?project_id={project_id}&rag=true", headers=headers)
    ids = {row["id"] for row in response.json()["data"]}
    assert rag_id in ids
    assert plain_id not in ids
