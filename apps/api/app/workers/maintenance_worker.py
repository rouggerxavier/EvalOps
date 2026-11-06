"""Worker cron: daily maintenance cleanup (expired revoked tokens and exports)."""
from __future__ import annotations

import asyncio
import logging
import os

from app.maintenance.cleanup import _totals, run_all

logger = logging.getLogger("evalops.worker.maintenance")

DEFAULT_MAINTENANCE_HOUR = 3


def maintenance_hour() -> int:
    """Hour (0-23, worker clock) for the daily cleanup; EVALOPS_MAINTENANCE_HOUR overrides."""
    raw = os.environ.get("EVALOPS_MAINTENANCE_HOUR", "").strip()
    try:
        hour = int(raw)
    except ValueError:
        return DEFAULT_MAINTENANCE_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_MAINTENANCE_HOUR


def _cleanup(db_factory) -> dict:
    with db_factory() as db:
        return _totals(run_all(db, dry_run=False))


async def maintenance_cleanup_job(ctx: dict) -> dict:
    totals = await asyncio.to_thread(_cleanup, ctx["db_session_factory"])
    logger.info("maintenance.cron_done", extra={"event": "maintenance.cron_done", **totals})
    return totals
