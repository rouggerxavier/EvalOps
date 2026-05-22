"""Fase E — integration test for rerun → replay → completed.

Bridges Fase C (rota enfileira) com Fase B (worker executa) sem precisar
de Redis ou worker rodando: invoca `replay_trace` diretamente como o arq
worker faria, valida estado final no DB e os logs estruturados emitidos.

Critério de done da spec: nenhum trace com `status="partial"` e
`duration_ms=0` após o fluxo completo.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.domain.evaluators import llm_judge
from app.main import app
from app.models import Span, Trace, User
from app.security import create_access_token, new_id
from app.workers.replay_worker import replay_trace


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _auth_header(user_id: str = "usr_1") -> dict[str, str]:
    token = create_access_token(sub=user_id, email="u1@example.com", name="U")
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> tuple[dict[str, str], str, str]:
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="U"))
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


def _ingest_trace_with_llm_span(client: TestClient, api_key: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": "ct_orig",
                "name": "rag.answer.compose",
                "service": "aurora-rag",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=500)).isoformat(),
                "status": "ok",
                "tags": {},
                "metadata": {},
                "spans": [
                    {
                        "client_span_id": "sp_llm",
                        "type": "llm_call",
                        "name": "llm.generate",
                        "started_at": now.isoformat(),
                        "ended_at": (now + timedelta(milliseconds=400)).isoformat(),
                        "status": "ok",
                        "provider": "openai",
                        "model": "gpt-4o-mini",
                        "messages_in": [{"role": "user", "content": "Olá {{nome}}"}],
                        "messages_out": [{"role": "assistant", "content": "Oi!"}],
                        "tokens_in": 5,
                        "tokens_out": 3,
                        "events": [],
                    }
                ],
            }
        ]
    }
    response = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert response.status_code == 202, response.text
    return response.json()["results"][0]["trace_id"]


def test_rerun_then_replay_produces_completed_trace_with_nonzero_metrics(
    monkeypatch, caplog, fake_arq_pool
) -> None:
    fake_arq_pool.jobs.clear()
    client = TestClient(app)
    headers, _project_id, api_key = _bootstrap(client)
    original_id = _ingest_trace_with_llm_span(client, api_key)

    rerun_resp = client.post(
        f"/v1/traces/{original_id}/rerun",
        headers=headers,
        json={"model": None, "variables": {"nome": "Alice"}},
    )
    assert rerun_resp.status_code == 200, rerun_resp.text
    new_trace_id = rerun_resp.json()["new_trace_id"]
    assert rerun_resp.json()["replay_status"] == "queued"

    enqueued = [job for job in fake_arq_pool.jobs if job[0] == "replay_trace"]
    assert enqueued, "Fase C deveria ter enfileirado replay_trace"
    job_kwargs = enqueued[-1][2]
    assert job_kwargs["original_trace_id"] == original_id
    assert job_kwargs["new_trace_id"] == new_trace_id

    with SessionLocal() as db:
        placeholder = db.get(Trace, new_trace_id)
        assert placeholder is not None
        assert placeholder.status == "partial"
        assert placeholder.duration_ms == 0
        assert placeholder.metadata_json["replay_status"] == "queued"

    def fake_call_llm(model: str, messages: list[dict], temperature: float) -> str:
        assert messages[0]["content"] == "Olá Alice", "variáveis devem ser substituídas"
        return "resposta replayed"

    monkeypatch.setattr(llm_judge, "call_llm", fake_call_llm)

    # ``configure_logging`` (run by lifespan in earlier tests) sets
    # propagate=False on the ``evalops`` logger, which prevents
    # pytest's caplog (attached to root) from seeing child records.
    # Force propagation just for this test.
    evalops_logger = logging.getLogger("evalops")
    monkeypatch.setattr(evalops_logger, "propagate", True)
    caplog.set_level(logging.INFO, logger="evalops.worker.replay")
    ctx = {"db_session_factory": SessionLocal}
    result = asyncio.run(replay_trace(ctx, original_id, new_trace_id))

    assert result["status"] == "completed"
    assert result["new_trace_id"] == new_trace_id
    assert result["duration_ms"] >= 0
    assert result["tokens_out"] > 0

    with SessionLocal() as db:
        completed = db.get(Trace, new_trace_id)
        assert completed is not None
        assert completed.status == "ok"
        assert completed.duration_ms >= 0
        assert completed.total_tokens_in > 0
        assert completed.total_tokens_out > 0
        assert completed.metadata_json["replay_status"] == "completed"
        assert "replay_started_at" in completed.metadata_json
        assert "replay_finished_at" in completed.metadata_json
        spans = db.query(Span).filter(Span.trace_id == new_trace_id).all()
        assert len(spans) == 1
        assert spans[0].messages_out[0]["content"] == "resposta replayed"
        assert spans[0].provider == "openai"
        assert spans[0].model == "gpt-4o-mini"

    msgs = [r.message for r in caplog.records if r.name == "evalops.worker.replay"]
    assert "replay.started" in msgs
    assert "replay.completed" in msgs


def test_replay_failure_logs_structured_event(monkeypatch, caplog, fake_arq_pool) -> None:
    fake_arq_pool.jobs.clear()
    client = TestClient(app)
    headers, _project_id, api_key = _bootstrap(client)
    original_id = _ingest_trace_with_llm_span(client, api_key)
    rerun = client.post(
        f"/v1/traces/{original_id}/rerun",
        headers=headers,
        json={"model": None, "variables": {}},
    )
    new_trace_id = rerun.json()["new_trace_id"]

    def boom(*args, **kwargs):
        raise RuntimeError("upstream_503")

    monkeypatch.setattr(llm_judge, "call_llm", boom)

    evalops_logger = logging.getLogger("evalops")
    monkeypatch.setattr(evalops_logger, "propagate", True)
    caplog.set_level(logging.ERROR, logger="evalops.worker.replay")
    ctx = {"db_session_factory": SessionLocal}
    result = asyncio.run(replay_trace(ctx, original_id, new_trace_id))

    assert result["status"] == "failed"
    assert result["reason"] == "RuntimeError"

    with SessionLocal() as db:
        ph = db.get(Trace, new_trace_id)
        assert ph is not None
        assert ph.metadata_json["replay_status"] == "failed"
        assert ph.metadata_json["replay_error"] == "RuntimeError"

    failure_msgs = [r for r in caplog.records if r.name == "evalops.worker.replay" and r.levelname == "ERROR"]
    assert any(r.message == "replay.failed" for r in failure_msgs)


def test_no_zombie_partial_traces_after_replay(monkeypatch, fake_arq_pool) -> None:
    """Critério de done da spec: zero traces com status=partial e duration_ms=0
    após o fluxo completo de rerun + replay."""
    fake_arq_pool.jobs.clear()
    client = TestClient(app)
    headers, _project_id, api_key = _bootstrap(client)
    original_id = _ingest_trace_with_llm_span(client, api_key)
    rerun = client.post(
        f"/v1/traces/{original_id}/rerun",
        headers=headers,
        json={"model": None, "variables": {}},
    )
    new_trace_id = rerun.json()["new_trace_id"]

    monkeypatch.setattr(llm_judge, "call_llm", lambda *_a, **_k: "ok")
    ctx = {"db_session_factory": SessionLocal}
    asyncio.run(replay_trace(ctx, original_id, new_trace_id))

    with SessionLocal() as db:
        zombies = (
            db.query(Trace)
            .filter(Trace.status == "partial", Trace.duration_ms == 0)
            .all()
        )
        assert zombies == [], f"esperado zero traces partial com duration_ms=0, encontrados: {[t.id for t in zombies]}"
