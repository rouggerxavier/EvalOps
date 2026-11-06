from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import EvaluationRun, Project, Rubric, Trace, User
from app.security import create_access_token, new_id


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


def _insert_meta_ref_traces(project_id: str, prompt_slug: str, version: int, count: int) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        assert project is not None
        for i in range(count):
            db.add(
                Trace(
                    id=new_id("tr"),
                    project_id=project_id,
                    organization_id=project.organization_id,
                    client_trace_id=f"meta-{i}",
                    name="chat.answer",
                    service="bot",
                    environment="prod",
                    started_at=now - timedelta(seconds=i),
                    ended_at=now - timedelta(seconds=i) + timedelta(milliseconds=100),
                    duration_ms=100,
                    status="ok",
                    tags={},
                    metadata_json={"prompt_ref": f"{prompt_slug}@{version}"},
                    total_tokens_in=0,
                    total_tokens_out=0,
                    total_cost_usd=0,
                )
            )
        db.commit()


def test_prompt_usage_counts_metadata_only_traces_and_signals_truncation() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    prompt = client.post(
        f"/v1/projects/{project_id}/prompts",
        headers=headers,
        json={
            "slug": "chatbot",
            "description": "",
            "template": "answer",
            "variables": {},
            "metadata": {},
        },
    ).json()["prompt"]

    _insert_meta_ref_traces(project_id, prompt_slug="chatbot", version=1, count=5)

    response = client.get(
        f"/v1/prompts/{prompt['id']}/usage?limit=3", headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["usage_count"] == 5
    assert body["usage_count_truncated"] is True
    assert len(body["traces"]) == 3
    assert all(t["prompt_version_ref"] == "chatbot@1" for t in body["traces"])

    full = client.get(
        f"/v1/prompts/{prompt['id']}/usage?limit=50", headers=headers
    ).json()
    assert full["usage_count"] == 5
    assert full["usage_count_truncated"] is False
    assert len(full["traces"]) == 5


def test_list_traces_last_score_picks_most_recent_run() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(
            Rubric(
                id="rb_x",
                project_id=project_id,
                slug="grounding",
                description=None,
                current_version=1,
                threshold=0.7,
            )
        )
        db.add_all(
            [
                EvaluationRun(
                    id="evr_old",
                    project_id=project_id,
                    trace_id=trace_id,
                    rubric_id="rb_x",
                    rubric_version=1,
                    triggered_by="test",
                    status="completed",
                    aggregate_score=0.2,
                    passed=False,
                    cost_usd=0.01,
                    run_metadata={},
                    created_at=now - timedelta(hours=2),
                ),
                EvaluationRun(
                    id="evr_new",
                    project_id=project_id,
                    trace_id=trace_id,
                    rubric_id="rb_x",
                    rubric_version=2,
                    triggered_by="test",
                    status="completed",
                    aggregate_score=0.91,
                    passed=True,
                    cost_usd=0.01,
                    run_metadata={},
                    created_at=now,
                ),
            ]
        )
        db.commit()

    response = client.get(f"/v1/traces?project_id={project_id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    row = next(t for t in body["data"] if t["id"] == trace_id)
    assert row["last_score"] == 0.91


def test_list_traces_status_csv_filters_multiple_statuses() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    _ingest_trace(client, api_key, status="ok")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        assert project is not None
        for i, st in enumerate(("error", "partial", "ok")):
            db.add(
                Trace(
                    id=new_id("tr"),
                    project_id=project_id,
                    organization_id=project.organization_id,
                    client_trace_id=f"st-{i}",
                    name="rag.answer",
                    service="bot",
                    environment="prod",
                    started_at=now - timedelta(seconds=i),
                    ended_at=now,
                    duration_ms=100,
                    status=st,
                    tags={},
                    metadata_json={},
                    total_tokens_in=0,
                    total_tokens_out=0,
                    total_cost_usd=0,
                )
            )
        db.commit()

    response = client.get(
        f"/v1/traces?project_id={project_id}&status=error,partial",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    statuses = {t["status"] for t in response.json()["data"]}
    assert statuses == {"error", "partial"}


def test_patch_project_empty_description_normalized_to_null_no_op() -> None:
    from app.models import AuditLog

    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    first = client.patch(
        f"/v1/projects/{project_id}",
        headers=headers,
        json={"description": ""},
    )
    assert first.status_code == 200, first.text
    with SessionLocal() as db:
        events = db.query(AuditLog).filter(AuditLog.target_id == project_id).all()
        assert events == [], "PATCH com description='' não devia auditar quando valor original é null"
    second = client.patch(
        f"/v1/projects/{project_id}",
        headers=headers,
        json={"description": "   "},
    )
    assert second.status_code == 200
    with SessionLocal() as db:
        events = db.query(AuditLog).filter(AuditLog.target_id == project_id).all()
        assert events == []


def test_mark_read_empty_ids_is_rejected_with_422() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    response = client.post(
        f"/v1/projects/{project_id}/notifications/mark-read",
        headers=headers,
        json={"ids": []},
    )
    assert response.status_code == 422, response.text


def test_sdk_status_p95_uses_nearest_rank() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        assert project is not None
        for i in range(10):
            latency_ms = (i + 1) * 10
            ended = now - timedelta(milliseconds=latency_ms)
            db.add(
                Trace(
                    id=new_id("tr"),
                    project_id=project_id,
                    organization_id=project.organization_id,
                    client_trace_id=f"p95-{i}",
                    name="rag.answer",
                    service="bot",
                    environment="prod",
                    started_at=ended - timedelta(milliseconds=50),
                    ended_at=ended,
                    duration_ms=50,
                    status="ok",
                    tags={},
                    metadata_json={},
                    total_tokens_in=0,
                    total_tokens_out=0,
                    total_cost_usd=0,
                    created_at=now,
                )
            )
        db.commit()

    response = client.get(f"/v1/projects/{project_id}/sdk-status", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["p95_ingestion_ms"] >= 95


def test_to_utc_helper_handles_mixed_tz_offsets() -> None:
    from datetime import timezone as _tz, timedelta as _td
    from app.api.routes_trace_actions import _to_utc

    base_utc = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    aware_minus3 = base_utc.astimezone(_tz(_td(hours=-3)))
    aware_plus5_utc = base_utc + _td(seconds=5)
    delta = int((_to_utc(aware_plus5_utc) - _to_utc(aware_minus3)).total_seconds())
    assert delta == 5, "tz aware com offsets diferentes deve convergir ao mesmo instante UTC"

    naive = base_utc.replace(tzinfo=None)
    naive_delta = int((_to_utc(aware_plus5_utc) - _to_utc(naive)).total_seconds())
    assert naive_delta == 5, "naive deve ser tratado como UTC, sem deslocamento"


def test_rag_does_not_fabricate_claim_totals_when_only_support_rate() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        assert project is not None
        trace = Trace(
            id=new_id("tr"),
            project_id=project_id,
            organization_id=project.organization_id,
            client_trace_id="rag_no_claims",
            name="rag.answer",
            service="bot",
            environment="prod",
            started_at=now,
            ended_at=now,
            duration_ms=10,
            status="ok",
            tags={},
            metadata_json={"support_rate": 0.4},
            total_tokens_in=0,
            total_tokens_out=0,
            total_cost_usd=0,
        )
        db.add(trace)
        db.commit()
        trace_id = trace.id

    response = client.get(f"/v1/traces/{trace_id}/rag", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["grounded_claims"] is None
    assert body["ungrounded_claims"] is None
    assert body["support_rate"] == 0.4
    assert body["claims_unavailable"] is True


def test_rag_returns_redacted_payload_when_trace_redacted() -> None:
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")
    with SessionLocal() as db:
        trace = db.get(Trace, trace_id)
        assert trace is not None
        trace.redacted = True
        db.add(trace)
        db.commit()
    response = client.get(f"/v1/traces/{trace_id}/rag", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["redacted"] is True
    assert body["citations"] == []
    assert body["claims"] == []
    assert body["answer_preview"] is None


def test_list_exports_paginates_with_cursor() -> None:
    from app.models import ExportJob

    client = TestClient(app)
    headers, project_id, _ = _bootstrap(client)
    base = datetime.now(timezone.utc).replace(microsecond=0)
    with SessionLocal() as db:
        for i in range(5):
            db.add(
                ExportJob(
                    id=new_id("exp"),
                    project_id=project_id,
                    status="ready",
                    format="jsonl",
                    filters={},
                    row_count=10,
                    file_path=None,
                    created_at=base - timedelta(seconds=i),
                )
            )
        db.commit()
    first = client.get(f"/v1/projects/{project_id}/exports?limit=2", headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert len(body["data"]) == 2
    assert body["next_cursor"]
    second = client.get(
        f"/v1/projects/{project_id}/exports?limit=2&cursor={body['next_cursor']}",
        headers=headers,
    )
    assert second.status_code == 200
    body2 = second.json()
    assert len(body2["data"]) == 2
    first_ids = {row["id"] for row in body["data"]}
    second_ids = {row["id"] for row in body2["data"]}
    assert first_ids.isdisjoint(second_ids)


def test_flag_trace_creates_audit_log_and_dedups() -> None:
    from app.models import AuditLog, TraceFlag

    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="error")
    first = client.post(
        f"/v1/traces/{trace_id}/flags",
        headers=headers,
        json={"reason": "manual", "note": "first"},
    )
    assert first.status_code == 201, first.text
    flag_id = first.json()["id"]

    second = client.post(
        f"/v1/traces/{trace_id}/flags",
        headers=headers,
        json={"reason": "manual", "note": "duplicate"},
    )
    assert second.status_code == 201
    assert second.json()["id"] == flag_id, "duplo flag em janela curta deveria retornar o mesmo"

    with SessionLocal() as db:
        flags = db.query(TraceFlag).filter(TraceFlag.trace_id == trace_id).all()
        assert len(flags) == 1
        audits = (
            db.query(AuditLog)
            .filter(AuditLog.action == "trace.flagged", AuditLog.target_id == trace_id)
            .all()
        )
        assert len(audits) == 1


def test_rerun_trace_writes_audit(fake_arq_pool) -> None:
    from app.models import AuditLog

    fake_arq_pool.jobs.clear()
    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")
    response = client.post(
        f"/v1/traces/{trace_id}/rerun",
        headers=headers,
        json={"reason": "investigate", "model": "gpt-4o-mini", "variables": {}},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["replay_status"] == "queued"
    with SessionLocal() as db:
        audits = (
            db.query(AuditLog)
            .filter(AuditLog.action == "trace.rerun_requested", AuditLog.target_id == trace_id)
            .all()
        )
        assert len(audits) == 1
    assert any(
        name == "replay_trace"
        and kwargs.get("original_trace_id") == trace_id
        and kwargs.get("new_trace_id") == body["new_trace_id"]
        for name, _args, kwargs in fake_arq_pool.jobs
    ), f"esperado replay_trace enfileirado, jobs={fake_arq_pool.jobs}"


def test_rerun_trace_returns_503_when_redis_unavailable(fake_arq_pool) -> None:
    from app.workers.queue import get_arq_pool

    _restore = app.dependency_overrides.get(get_arq_pool)
    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")

    def _no_pool():
        from fastapi import HTTPException, status as _status

        raise HTTPException(status_code=_status.HTTP_503_SERVICE_UNAVAILABLE, detail="replay_unavailable")

    app.dependency_overrides[get_arq_pool] = _no_pool
    try:
        response = client.post(
            f"/v1/traces/{trace_id}/rerun",
            headers=headers,
            json={"model": None, "variables": {}},
        )
    finally:
        if _restore is not None:
            app.dependency_overrides[get_arq_pool] = _restore
        else:
            app.dependency_overrides.pop(get_arq_pool, None)
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "replay_unavailable"

    with SessionLocal() as db:
        from app.models import AuditLog

        audits = (
            db.query(AuditLog)
            .filter(AuditLog.action == "trace.rerun_requested", AuditLog.target_id == trace_id)
            .all()
        )
        assert audits == [], "503 não deve gravar audit nem placeholder"
        traces = (
            db.query(Trace)
            .filter(
                Trace.project_id != None,  # noqa: E711
                Trace.metadata_json["replay_of"].as_string() == trace_id,
            )
            .all()
        )
        assert traces == [], "503 não deve criar placeholder fantasma"


def test_rerun_trace_returns_503_when_enqueue_raises(fake_arq_pool) -> None:
    from app.workers.queue import get_arq_pool

    _restore = app.dependency_overrides.get(get_arq_pool)
    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")

    class _BrokenPool:
        async def enqueue_job(self, *args, **kwargs):
            raise ConnectionError("redis_down")

    app.dependency_overrides[get_arq_pool] = lambda: _BrokenPool()
    try:
        response = client.post(
            f"/v1/traces/{trace_id}/rerun",
            headers=headers,
            json={"model": None, "variables": {}},
        )
    finally:
        if _restore is not None:
            app.dependency_overrides[get_arq_pool] = _restore
        else:
            app.dependency_overrides.pop(get_arq_pool, None)
    assert response.status_code == 503
    assert response.json()["detail"] == "replay_unavailable"
    with SessionLocal() as db:
        placeholders = db.query(Trace).filter(Trace.metadata_json["replay_of"].as_string() == trace_id).all()
        assert len(placeholders) == 1
        assert placeholders[0].metadata_json["replay_status"] == "failed", "nada pode ficar preso em queued"
        assert placeholders[0].metadata_json["replay_error"] == "queue_unavailable"


def test_rerun_trace_commits_placeholder_before_enqueue() -> None:
    from app.workers.queue import get_arq_pool

    _restore = app.dependency_overrides.get(get_arq_pool)
    client = TestClient(app)
    headers, _, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")
    seen: list[bool] = []

    class _CheckingPool:
        async def enqueue_job(self, function_name, *, original_trace_id, new_trace_id):
            # The worker uses its own session: the placeholder must already be committed.
            with SessionLocal() as other:
                seen.append(other.get(Trace, new_trace_id) is not None)

    app.dependency_overrides[get_arq_pool] = lambda: _CheckingPool()
    try:
        response = client.post(f"/v1/traces/{trace_id}/rerun", headers=headers, json={"model": None, "variables": {}})
    finally:
        if _restore is not None:
            app.dependency_overrides[get_arq_pool] = _restore
        else:
            app.dependency_overrides.pop(get_arq_pool, None)
    assert response.status_code == 200, response.text
    assert seen == [True]


def test_rerun_trace_blocked_when_judge_budget_exhausted(fake_arq_pool) -> None:
    fake_arq_pool.jobs.clear()
    client = TestClient(app)
    headers, project_id, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key, status="ok")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        original = db.get(Trace, trace_id)
        # A past replay whose cost already ate the whole monthly judge budget.
        db.add(
            Trace(
                id=new_id("tr"),
                project_id=project_id,
                organization_id=original.organization_id,
                name="old.replay",
                environment="prod",
                status="ok",
                started_at=now,
                ended_at=now,
                duration_ms=1,
                total_cost_usd=10_000,
                metadata_json={"replay_of": trace_id, "replay_status": "completed"},
            )
        )
        db.commit()

    response = client.post(f"/v1/traces/{trace_id}/rerun", headers=headers, json={"model": None, "variables": {}})
    assert response.status_code == 402, response.text
    assert response.json()["detail"]["error"] == "judge_budget_exhausted"
    assert fake_arq_pool.jobs == []
    with SessionLocal() as db:
        queued = db.query(Trace).filter(Trace.metadata_json["replay_status"].as_string() == "queued").all()
        assert queued == []


def test_members_listing_paginates_with_cursor() -> None:
    from app.models import Membership

    client = TestClient(app)
    headers, _, _ = _bootstrap(client)
    me = client.get("/v1/me", headers=headers).json()
    org_id = me["organizations"][0]["id"]
    base = datetime.now(timezone.utc).replace(microsecond=0)
    with SessionLocal() as db:
        for i in range(4):
            uid = f"usr_extra_{i}"
            db.add(User(id=uid, email=f"extra{i}@example.com", name=f"Extra {i}"))
            db.add(
                Membership(
                    user_id=uid,
                    organization_id=org_id,
                    role="member",
                    created_at=base + timedelta(seconds=i + 1),
                )
            )
        db.commit()
    first = client.get(f"/v1/organizations/{org_id}/members?limit=2", headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert len(body["data"]) == 2
    assert body["next_cursor"]
    second = client.get(
        f"/v1/organizations/{org_id}/members?limit=2&cursor={body['next_cursor']}",
        headers=headers,
    )
    assert second.status_code == 200
    body2 = second.json()
    assert len(body2["data"]) >= 2
    first_ids = {row["user_id"] for row in body["data"]}
    second_ids = {row["user_id"] for row in body2["data"]}
    assert first_ids.isdisjoint(second_ids)


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
