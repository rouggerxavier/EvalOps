"""Execution coordination, also run with SAMPLING_TEST_DATABASE_URL on dedicated PG16."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event

import pytest
from arq import Retry
from sqlalchemy import event, text

from app.domain.evaluators.base import EvaluatorResult
from app.domain.services import eval_service
from app.domain.services.sampling_service import process_sample
from app.domain.services.trace_lock_service import trace_execution_lock
from app.models import Trace
from app.workers.evaluation_worker import _evaluate
from app.workers.replay_worker import replay_trace
from test_sampling import env, configure, ingest


@pytest.mark.parametrize("entrypoint", ["manual", "batch", "sampling"])
def test_evaluation_providers_are_idle_and_all_executors_share_lock(env, monkeypatch, entrypoint):
    configure(env)
    trace_id = ingest(env)
    entered, release = Event(), Event()
    calls, final_commits = [], []
    provider_finished = Event()
    original = eval_service.run_evaluation
    active = {}

    def track(**kwargs):
        active["db"] = kwargs["db"]
        def final_commit(session):
            if provider_finished.is_set():
                with env["factory"]() as other, trace_execution_lock(other, trace_id) as acquired:
                    assert not acquired
                final_commits.append(True)
        event.listen(kwargs["db"], "before_commit", final_commit)
        return original(**kwargs)

    def provider(context, config):
        db = active["db"]
        assert not db.in_transaction()
        bind = db.get_bind()
        if bind.dialect.name == "postgresql":
            raw = bind.connection.driver_connection
            status = raw.info.transaction_status if hasattr(raw, "info") else raw.get_transaction_status()
            assert status == 0
        calls.append(context)
        entered.set()
        assert release.wait(10)
        provider_finished.set()
        return EvaluatorResult(score=1, passed=True, cost_usd=0.03)

    monkeypatch.setattr(eval_service, "run_evaluation", track)
    monkeypatch.setitem(eval_service.REGISTRY, "length_bounds", provider)

    def manual():
        return env["client"].post("/v1/evaluations/run", headers=env["headers"],
                                  json={"trace_id": trace_id, "rubric_id": env["rubric"]})

    def batch():
        return _evaluate(env["factory"], trace_id, env["rubric"], 1, "batch")

    task = {"manual": manual, "batch": batch,
            "sampling": lambda: process_sample(env["factory"], trace_id)}[entrypoint]
    with ThreadPoolExecutor() as executor:
        pending = executor.submit(task)
        try:
            assert entered.wait(10)
            response = manual()
            assert response.status_code == 409 and response.json()["detail"] == "trace_busy"
            assert batch() == {"status": "busy"}
            assert process_sample(env["factory"], trace_id) == {"status": "busy"}
            with pytest.raises(Retry):
                asyncio.run(replay_trace({"db_session_factory": env["factory"]}, trace_id, "destination"))
        finally:
            release.set()
        result = pending.result(10)
        assert result.status_code == 201 if entrypoint == "manual" else result["status"] == "completed"
    assert len(calls) == 1
    assert final_commits == [True]
    with env["factory"]() as db, trace_execution_lock(db, trace_id) as acquired:
        assert acquired


def test_deleted_trace_jobs_never_call_provider(env, monkeypatch):
    configure(env)
    trace_id = ingest(env)
    with env["factory"]() as db:
        trace = db.get(Trace, trace_id)
        from app.models import utcnow
        trace.deleted_at = utcnow()
        db.commit()
    def unexpected(*args, **kwargs):
        pytest.fail("provider called for deleted trace")
    monkeypatch.setitem(eval_service.REGISTRY, "length_bounds", unexpected)
    assert _evaluate(env["factory"], trace_id, env["rubric"], 1, "batch")["reason"] == "not_found"
    assert process_sample(env["factory"], trace_id)["reason"] == "not_found"
    assert asyncio.run(replay_trace({"db_session_factory": env["factory"]}, "missing", trace_id))["status"] == "failed"


def test_ordered_multi_lock_releases_partial_acquisition(env):
    with env["factory"]() as first, env["factory"]() as second:
        with trace_execution_lock(first, ["b", "a", "a"]) as acquired:
            assert acquired
            first.execute(text("SELECT 1"))
            first.commit()
            with trace_execution_lock(second, ["a", "b"]) as acquired:
                assert not acquired
        with trace_execution_lock(second, ["b", "a"]) as acquired:
            assert acquired


@pytest.mark.parametrize("fail", [False, True])
def test_replay_holds_both_locks_through_settlement_and_final_commit(env, monkeypatch, fail):
    from decimal import Decimal
    from types import SimpleNamespace
    from sqlalchemy import event
    from app.workers import replay_worker

    configure(env)
    original_id, destination_id = ingest(env, "original"), ingest(env, "destination")
    with env["factory"]() as db:
        destination = db.get(Trace, destination_id)
        destination.metadata_json = {"replay_status": "queued", "replay_of": original_id}
        db.commit()
    real_factory = env["factory"]
    sessions, checked_commits = [], []
    def factory():
        db = real_factory()
        sessions.append(db)
        return db

    def both_busy():
        for trace_id in [original_id, destination_id]:
            with real_factory() as other, trace_execution_lock(other, trace_id) as acquired:
                assert not acquired

    async def provider(*args, **kwargs):
        db = sessions[0]
        assert not db.in_transaction()
        if db.get_bind().dialect.name == "postgresql":
            raw = db.get_bind().connection.driver_connection
            assert (raw.info.transaction_status if hasattr(raw, "info") else raw.get_transaction_status()) == 0
        both_busy()
        # Check again at every post-provider commit, including failure status.
        event.listen(db, "before_commit", lambda session: (both_busy(), checked_commits.append(True)))
        if fail:
            raise RuntimeError("synthetic provider failure")
        return SimpleNamespace(cost_usd=Decimal("0.030000"), duration_ms=1,
                               tokens_in=1, tokens_out=1, provider="fake", model="fake",
                               messages_out_text="ok")

    monkeypatch.setattr(replay_worker, "_call_provider", provider)
    result = asyncio.run(replay_trace({"db_session_factory": factory}, original_id, destination_id))
    assert result["status"] == ("failed" if fail else "completed")
    assert len(checked_commits) == (1 if fail else 3)
    for trace_id in [original_id, destination_id]:
        with real_factory() as db, trace_execution_lock(db, trace_id) as acquired:
            assert acquired


def test_postgres_partial_multi_lock_is_released_before_retry(env):
    with env["factory"]() as first, env["factory"]() as second, env["factory"]() as third:
        if first.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL per-trace advisory locks")
        with trace_execution_lock(first, "b") as acquired:
            assert acquired
            with trace_execution_lock(second, ["b", "a"]) as acquired:
                assert not acquired
            with trace_execution_lock(third, "a") as acquired:
                assert acquired


def test_batch_busy_uses_arq_retry_without_evaluation(env, monkeypatch):
    from app.workers.evaluation_worker import evaluate_trace_job
    configure(env)
    trace_id = ingest(env)
    with env["factory"]() as db, trace_execution_lock(db, trace_id) as acquired:
        assert acquired
        with pytest.raises(Retry):
            asyncio.run(evaluate_trace_job({"db_session_factory": env["factory"]}, trace_id, env["rubric"], 1))


def test_redelivered_terminal_replay_keeps_status_without_provider(env, monkeypatch):
    from app.workers import replay_worker
    configure(env)
    original_id, destination_id = ingest(env, "original"), ingest(env, "destination")
    with env["factory"]() as db:
        db.get(Trace, destination_id).metadata_json = {"replay_status": "completed", "replay_of": original_id}
        db.get(Trace, original_id).deleted_at = datetime.now(timezone.utc)
        db.commit()

    async def unexpected(*args, **kwargs):
        pytest.fail("provider called for settled replay")

    monkeypatch.setattr(replay_worker, "_call_provider", unexpected)
    result = asyncio.run(replay_trace({"db_session_factory": env["factory"]}, original_id, destination_id))
    assert result == {"status": "completed"}
    with env["factory"]() as db:
        assert db.get(Trace, destination_id).metadata_json["replay_status"] == "completed"
