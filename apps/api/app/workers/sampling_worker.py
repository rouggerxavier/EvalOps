"""Bounded outbox dispatch and automatic evaluation on the existing arq worker."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from app.domain.services.sampling_service import process_sample
from app.models import EvaluationSamplingJob, utcnow

logger = logging.getLogger("evalops.worker.sampling")


async def dispatch_sampling_job(ctx: dict) -> dict:
    now = utcnow()
    enqueued = failed = 0
    with ctx["db_session_factory"]() as db:
        jobs = db.query(EvaluationSamplingJob).filter(
            EvaluationSamplingJob.status.in_(["pending", "queue_error", "queued"]),
            EvaluationSamplingJob.next_attempt_at <= now,
        ).order_by(EvaluationSamplingJob.next_attempt_at).limit(100).with_for_update(skip_locked=True).all()
        for job in jobs:
            try:
                result = await ctx["redis"].enqueue_job(
                    "evaluate_sample_job", trace_id=job.trace_id,
                    _job_id=f"sample:{job.trace_id}:{job.dispatch_attempts + 1}",
                )
                job.status, job.reason = "queued", None
                job.dispatch_attempts += 1
                # Recovery for a queue lost after enqueue acknowledgement; execution is idempotent.
                job.next_attempt_at = now + timedelta(minutes=5)
                enqueued += int(result is not None)
            except Exception:
                job.status, job.reason = "queue_error", "evaluation_queue_unavailable"
                job.next_attempt_at = now + timedelta(minutes=1)
                failed += 1
            job.updated_at = now
        db.commit()
    logger.info("sampling.dispatched enqueued=%s failed=%s", enqueued, failed,
                extra={"event": "sampling.dispatched"})
    return {"enqueued": enqueued, "failed": failed}


async def evaluate_sample_job(ctx: dict, trace_id: str) -> dict:
    result = await asyncio.to_thread(process_sample, ctx["db_session_factory"], trace_id)
    logger.info("sampling.evaluated trace_id=%s status=%s reason=%s", trace_id, result["status"], result.get("reason"),
                extra={"event": "sampling.evaluated"})
    return result
