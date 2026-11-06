"""Worker cron: daily maintenance cleanup (expired revoked tokens and exports)."""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.maintenance.cleanup import _totals, run_all

logger = logging.getLogger("evalops.worker.maintenance")

DEFAULT_MAINTENANCE_HOUR = 3
CLEANUP_BATCH_SIZE = 1000


def maintenance_timezone() -> tzinfo:
    """Timezone of the cron schedule; EVALOPS_MAINTENANCE_TZ (IANA name) overrides, UTC by default."""
    # timezone.utc needs no tz database, which slim images may lack.
    raw = os.environ.get("EVALOPS_MAINTENANCE_TZ", "").strip()
    if not raw or raw.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("maintenance.bad_timezone", extra={"event": "maintenance.bad_timezone"})
        return timezone.utc


def maintenance_hour() -> int:
    """Hour (0-23, in maintenance_timezone) for the daily cleanup; EVALOPS_MAINTENANCE_HOUR overrides."""
    raw = os.environ.get("EVALOPS_MAINTENANCE_HOUR", "").strip()
    try:
        hour = int(raw)
    except ValueError:
        return DEFAULT_MAINTENANCE_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_MAINTENANCE_HOUR


def _cleanup(db_factory) -> dict:
    # Bounded batches, each committed by the cleanup services, so a backlog never runs into job_timeout as one pass.
    summaries = []
    with db_factory() as db:
        while True:
            batch = run_all(db, dry_run=False, limit=CLEANUP_BATCH_SIZE)
            summaries.extend(batch)
            # Stop on a batch that deleted nothing: non-expired or unsafe rows stay and would loop forever.
            if not any(s.deleted_rows for s in batch):
                break
    return _totals(summaries)


async def maintenance_cleanup_job(ctx: dict) -> dict:
    totals = await asyncio.to_thread(_cleanup, ctx["db_session_factory"])
    logger.info("maintenance.cron_done", extra={"event": "maintenance.cron_done", **totals})
    return totals
