"""arq WorkerSettings — Fase A+B da spec async-worker-replay.

Run with: `python -m arq app.workers.settings.WorkerSettings`.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import redis_url, worker_concurrency
from app.workers.replay_worker import replay_trace

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


class WorkerSettings:
    functions: list = [replay_trace]
    redis_settings = _redis_settings()
    max_jobs = worker_concurrency()
    on_startup = startup
    on_shutdown = shutdown
