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


def test_worker_settings_cron_timezone_is_explicit(monkeypatch) -> None:
    from datetime import timezone
    from zoneinfo import ZoneInfo

    import app.workers.settings as settings_module

    monkeypatch.delenv("EVALOPS_MAINTENANCE_TZ", raising=False)
    importlib.reload(settings_module)
    assert settings_module.WorkerSettings.timezone is timezone.utc

    monkeypatch.setenv("EVALOPS_MAINTENANCE_TZ", "America/Sao_Paulo")
    importlib.reload(settings_module)
    assert settings_module.WorkerSettings.timezone == ZoneInfo("America/Sao_Paulo")

    monkeypatch.setenv("EVALOPS_MAINTENANCE_TZ", "Not/AZone")
    importlib.reload(settings_module)
    assert settings_module.WorkerSettings.timezone is timezone.utc
    monkeypatch.delenv("EVALOPS_MAINTENANCE_TZ", raising=False)
    importlib.reload(settings_module)


def test_maintenance_cleanup_job_applies_run_all_in_batches(monkeypatch) -> None:
    import asyncio
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import RevokedToken
    from app.workers import maintenance_worker

    monkeypatch.setattr(maintenance_worker, "CLEANUP_BATCH_SIZE", 2)
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for i in range(5):
            db.add(RevokedToken(jti=f"jti_old_{i}", expires_at=now - timedelta(days=1)))
        db.add(RevokedToken(jti="jti_live", expires_at=now + timedelta(days=1)))
        db.commit()
    totals = asyncio.run(maintenance_worker.maintenance_cleanup_job({"db_session_factory": SessionLocal}))
    assert totals["deleted_rows"] == 5
    with SessionLocal() as db:
        assert [row.jti for row in db.query(RevokedToken).all()] == ["jti_live"]


def test_worker_settings_registers_invitation_and_recovery():
    from app.workers.settings import WorkerSettings
    from app.workers.invitation_worker import send_invitation_job
    from app.workers.password_recovery_worker import send_password_reset_job
    assert send_invitation_job in WorkerSettings.functions
    assert send_password_reset_job in WorkerSettings.functions
