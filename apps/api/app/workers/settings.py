"""arq WorkerSettings — Fase A+B da spec async-worker-replay.

Run with: `python -m arq app.workers.settings.WorkerSettings`.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import redis_url, worker_concurrency
from app.domain.services.trace_lock_service import JOB_MAX_TRIES
from app.workers.evaluation_worker import evaluate_trace_job
from app.workers.maintenance_worker import maintenance_cleanup_job, maintenance_hour, maintenance_timezone
from app.workers.password_recovery_worker import send_password_reset_job
from app.workers.replay_worker import replay_trace
from app.workers.sampling_worker import dispatch_sampling_job, evaluate_sample_job

logger = logging.getLogger("evalops.worker")


def _redis_settings() -> Any:
    """Return arq.RedisSettings from REDIS_URL, or None to use library default."""
    from arq.connections import RedisSettings

    dsn = redis_url()
    if not dsn:
        return RedisSettings()
    return RedisSettings.from_dsn(dsn)


async def startup(ctx: dict) -> None:
    from app.db import SessionLocal

    ctx["db_session_factory"] = SessionLocal
    logger.info("worker.startup", extra={"functions": [f.__name__ for f in WorkerSettings.functions]})


async def shutdown(ctx: dict) -> None:
    logger.info("worker.shutdown")


def _cron_jobs() -> list:
    from arq import cron

    return [
        cron(maintenance_cleanup_job, hour=maintenance_hour(), minute=0),
        cron(dispatch_sampling_job, minute=set(range(60))),
    ]


class WorkerSettings:
    functions: list = [send_password_reset_job, replay_trace, evaluate_trace_job, evaluate_sample_job, dispatch_sampling_job]
    cron_jobs = _cron_jobs()
    # Cron hours are read in this zone, not the process clock.
    timezone = maintenance_timezone()
    redis_settings = _redis_settings()
    max_jobs = worker_concurrency()
    max_tries = JOB_MAX_TRIES
    on_startup = startup
    on_shutdown = shutdown
