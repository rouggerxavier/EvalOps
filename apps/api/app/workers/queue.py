"""arq pool lifecycle and FastAPI dependency (Fase C).

Pool is initialised in `app.main:lifespan` and exposed via
`request.app.state.arq_pool`. When Redis is unavailable at startup the
attribute is set to `None`; the rerun route then returns 503 per §C-1.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request, status

from app.config import redis_url

logger = logging.getLogger("evalops.queue")


async def create_arq_pool() -> Any | None:
    """Best-effort pool creation. Returns None if Redis is unreachable."""
    from arq import create_pool
    from arq.connections import RedisSettings

    dsn = redis_url()
    settings = RedisSettings.from_dsn(dsn) if dsn else RedisSettings()
    try:
        return await create_pool(settings)
    except Exception as exc:
        logger.warning("queue.pool_unavailable", extra={"reason": type(exc).__name__})
        return None


async def close_arq_pool(pool: Any | None) -> None:
    if pool is None:
        return
    try:
        await pool.aclose()
    except Exception:
        pass


def get_arq_pool(request: Request) -> Any:
    """Dependency: return the pool, or raise 503 if unavailable."""
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="replay_unavailable",
        )
    return pool
