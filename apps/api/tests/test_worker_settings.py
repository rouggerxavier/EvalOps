"""Fase A — worker infra smoke tests.

Validates that `WorkerSettings` imports cleanly with arq installed, exposes the
required attributes, and that `worker_concurrency()` honours the env override.
"""
from __future__ import annotations

import importlib
import os


def test_worker_settings_registers_replay_trace() -> None:
    from app.workers.replay_worker import replay_trace
    from app.workers.settings import WorkerSettings

    assert replay_trace in WorkerSettings.functions
    assert callable(WorkerSettings.on_startup)
    assert callable(WorkerSettings.on_shutdown)
    assert WorkerSettings.max_jobs >= 1


def test_worker_concurrency_env_override(monkeypatch) -> None:
    from app import config

    monkeypatch.setenv("EVALOPS_WORKER_CONCURRENCY", "7")
    assert config.worker_concurrency() == 7
    monkeypatch.delenv("EVALOPS_WORKER_CONCURRENCY", raising=False)
    assert config.worker_concurrency() == 4


def test_worker_settings_redis_settings_uses_url(monkeypatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://example.invalid:6380/2")
    import app.workers.settings as settings_module

    importlib.reload(settings_module)
    rs = settings_module.WorkerSettings.redis_settings
    assert rs.host == "example.invalid"
    assert rs.port == 6380
    assert rs.database == 2
    monkeypatch.delenv("REDIS_URL", raising=False)
    importlib.reload(settings_module)


def test_worker_settings_schedules_daily_maintenance_cleanup(monkeypatch) -> None:
    import app.workers.settings as settings_module
    from app.workers.maintenance_worker import maintenance_cleanup_job

    def _cleanup_cron():
        jobs = [job for job in settings_module.WorkerSettings.cron_jobs if job.coroutine is maintenance_cleanup_job]
        assert len(jobs) == 1
        return jobs[0]

    monkeypatch.delenv("EVALOPS_MAINTENANCE_HOUR", raising=False)
    importlib.reload(settings_module)
    assert (_cleanup_cron().hour, _cleanup_cron().minute) == (3, 0)

    monkeypatch.setenv("EVALOPS_MAINTENANCE_HOUR", "22")
    importlib.reload(settings_module)
    assert _cleanup_cron().hour == 22

    monkeypatch.setenv("EVALOPS_MAINTENANCE_HOUR", "99")
    importlib.reload(settings_module)
    assert _cleanup_cron().hour == 3
    monkeypatch.delenv("EVALOPS_MAINTENANCE_HOUR", raising=False)
    importlib.reload(settings_module)


def test_maintenance_cleanup_job_applies_run_all() -> None:
    import asyncio
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import RevokedToken
    from app.workers.maintenance_worker import maintenance_cleanup_job

    with SessionLocal() as db:
        db.add(RevokedToken(jti="jti_old", expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
        db.commit()
    totals = asyncio.run(maintenance_cleanup_job({"db_session_factory": SessionLocal}))
    assert totals["deleted_rows"] >= 1
    with SessionLocal() as db:
        assert db.get(RevokedToken, "jti_old") is None
