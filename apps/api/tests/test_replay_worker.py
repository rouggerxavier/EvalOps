"""Unit tests for `replay_trace` (Fase B).

`llm_judge.call_llm` is monkeypatched so no real HTTP call is made.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.db import Base, SessionLocal, engine
from app.domain.evaluators import llm_judge
from app.models import Project, Span, Trace, User
from app.security import new_id
from app.workers.replay_worker import _build_messages, replay_trace


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _seed_project() -> tuple[str, str]:
    with SessionLocal() as db:
        org_id = new_id("org")
        from app.models import Organization

        db.add(Organization(id=org_id, name="Acme", slug="acme"))
        db.add(User(id="usr_1", email="u1@example.com", name="U"))
        project_id = new_id("proj")
        db.add(
            Project(
                id=project_id,
                organization_id=org_id,
                name="P",
                slug="p",
                default_environment="prod",
            )
        )
        db.commit()
        return org_id, project_id


def _seed_original_trace_with_llm_span(org_id: str, project_id: str) -> str:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        trace_id = new_id("tr")
        db.add(
            Trace(
                id=trace_id,
                project_id=project_id,
                organization_id=org_id,
                client_trace_id="orig",
                name="rag.answer",
                service="bot",
                environment="prod",
                started_at=now,
                ended_at=now,
                duration_ms=100,
                status="ok",
                tags={},
                metadata_json={},
                total_tokens_in=0,
                total_tokens_out=0,
                total_cost_usd=0,
            )
        )
        db.add(
            Span(
                id=new_id("sp"),
                trace_id=trace_id,
                type="llm_call",
                name="llm.generate",
                status="ok",
                started_at=now,
                ended_at=now,
                duration_ms=50,
                provider="openai",
                model="gpt-4o-mini",
                messages_in=[{"role": "user", "content": "Olá {{nome}}"}],
                messages_out=[{"role": "assistant", "content": "Oi!"}],
                tokens_in=2,
                tokens_out=2,
                cost_usd=0.0001,
            )
        )
        db.commit()
        return trace_id


def _seed_placeholder(org_id: str, project_id: str, original_id: str, **meta_overrides) -> str:
    now = datetime.now(timezone.utc)
    metadata = {"replay_of": original_id, "replay_status": "queued"}
    metadata.update(meta_overrides)
    with SessionLocal() as db:
        ph_id = new_id("tr")
        db.add(
            Trace(
                id=ph_id,
                project_id=project_id,
                organization_id=org_id,
                client_trace_id=None,
                name="rag.answer",
                service="bot",
                environment="prod",
                started_at=now,
                ended_at=now,
                duration_ms=0,
                status="partial",
                tags={},
                metadata_json=metadata,
                total_tokens_in=0,
                total_tokens_out=0,
                total_cost_usd=0,
            )
        )
        db.commit()
        return ph_id


def _ctx() -> dict:
    return {"db_session_factory": SessionLocal}


def test_replay_trace_transitions_to_completed(monkeypatch) -> None:
    org_id, project_id = _seed_project()
    original_id = _seed_original_trace_with_llm_span(org_id, project_id)
    placeholder_id = _seed_placeholder(org_id, project_id, original_id)

    captured: dict = {}

    def fake_call_llm(model: str, messages: list[dict], temperature: float) -> str:
        captured["model"] = model
        captured["messages"] = messages
        return "respondido"

    monkeypatch.setattr(llm_judge, "call_llm", fake_call_llm)

    result = asyncio.run(replay_trace(_ctx(), original_id, placeholder_id))
    assert result["status"] == "completed"
    assert captured["model"] == "gpt-4o-mini"

    with SessionLocal() as db:
        ph = db.get(Trace, placeholder_id)
        assert ph is not None
        assert ph.metadata_json["replay_status"] == "completed"
        assert "replay_finished_at" in ph.metadata_json
        assert ph.status == "ok"
        assert ph.total_tokens_out > 0
        spans = db.query(Span).filter(Span.trace_id == placeholder_id).all()
        assert len(spans) == 1
        assert spans[0].messages_out[0]["content"] == "respondido"


def test_replay_trace_no_llm_span_fails_gracefully(monkeypatch) -> None:
    org_id, project_id = _seed_project()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        original_id = new_id("tr")
        db.add(
            Trace(
                id=original_id,
                project_id=project_id,
                organization_id=org_id,
                client_trace_id="orig_no_llm",
                name="rag.answer",
                service="bot",
                environment="prod",
                started_at=now,
                ended_at=now,
                duration_ms=10,
                status="ok",
                tags={},
                metadata_json={},
                total_tokens_in=0,
                total_tokens_out=0,
                total_cost_usd=0,
            )
        )
        db.commit()
    placeholder_id = _seed_placeholder(org_id, project_id, original_id)

    def fake_call_llm(*args, **kwargs):  # pragma: no cover — should not be called
        raise AssertionError("call_llm não deveria ser chamado sem span LLM")

    monkeypatch.setattr(llm_judge, "call_llm", fake_call_llm)

    result = asyncio.run(replay_trace(_ctx(), original_id, placeholder_id))
    assert result == {"status": "failed", "reason": "no_llm_span_found"}

    with SessionLocal() as db:
        ph = db.get(Trace, placeholder_id)
        assert ph is not None
        assert ph.metadata_json["replay_status"] == "failed"
        assert ph.metadata_json["replay_error"] == "no_llm_span_found"


def test_replay_trace_substitutes_variables(monkeypatch) -> None:
    org_id, project_id = _seed_project()
    original_id = _seed_original_trace_with_llm_span(org_id, project_id)
    placeholder_id = _seed_placeholder(
        org_id, project_id, original_id, rerun_variables={"nome": "Alice"}
    )

    captured: dict = {}

    def fake_call_llm(model: str, messages: list[dict], temperature: float) -> str:
        captured["messages"] = messages
        return "OK"

    monkeypatch.setattr(llm_judge, "call_llm", fake_call_llm)

    asyncio.run(replay_trace(_ctx(), original_id, placeholder_id))
    assert captured["messages"][0]["content"] == "Olá Alice"


def test_replay_trace_model_override(monkeypatch) -> None:
    org_id, project_id = _seed_project()
    original_id = _seed_original_trace_with_llm_span(org_id, project_id)
    placeholder_id = _seed_placeholder(
        org_id, project_id, original_id, rerun_model="openai/gpt-4.1"
    )

    captured: dict = {}

    def fake_call_llm(model: str, messages: list[dict], temperature: float) -> str:
        captured["model"] = model
        return "OK"

    monkeypatch.setattr(llm_judge, "call_llm", fake_call_llm)

    asyncio.run(replay_trace(_ctx(), original_id, placeholder_id))
    assert captured["model"] == "openai/gpt-4.1"


def test_replay_trace_provider_error_marks_failed(monkeypatch) -> None:
    org_id, project_id = _seed_project()
    original_id = _seed_original_trace_with_llm_span(org_id, project_id)
    placeholder_id = _seed_placeholder(org_id, project_id, original_id)

    def boom(*args, **kwargs):
        raise RuntimeError("upstream_500")

    monkeypatch.setattr(llm_judge, "call_llm", boom)

    result = asyncio.run(replay_trace(_ctx(), original_id, placeholder_id))
    assert result["status"] == "failed"
    assert result["reason"] == "RuntimeError"

    with SessionLocal() as db:
        ph = db.get(Trace, placeholder_id)
        assert ph is not None
        assert ph.metadata_json["replay_status"] == "failed"
        assert ph.metadata_json["replay_error"] == "RuntimeError"
        assert ph.status == "partial"


def test_build_messages_handles_non_dict_entries_and_missing_content() -> None:
    span = Span(
        id="sp",
        trace_id="tr",
        type="llm_call",
        name="llm.generate",
        status="ok",
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=1,
        messages_in=[
            "not a dict",  # ignored
            {"role": "user"},  # missing content → ""
            {"role": "user", "content": "Olá {{name}}"},
        ],
    )
    msgs = _build_messages(span, {"name": "Bob"})
    assert len(msgs) == 2
    assert msgs[0] == {"role": "user", "content": ""}
    assert msgs[1] == {"role": "user", "content": "Olá Bob"}
