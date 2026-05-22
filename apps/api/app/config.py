"""Runtime configuration sourced from environment variables.

Lazy getters so tests can mutate ``os.environ`` between calls without
re-importing the module.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_SPANS_PER_TRACE = 500


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def max_body_bytes() -> int:
    return _positive_int("EVALOPS_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES)


def max_spans_per_trace() -> int:
    return _positive_int("EVALOPS_MAX_SPANS_PER_TRACE", DEFAULT_MAX_SPANS_PER_TRACE)


def exports_dir() -> Path:
    """Return an absolute, guaranteed-to-exist directory for export files (G-10).

    Override with EVALOPS_EXPORTS_DIR to decouple from the uvicorn CWD.
    Default resolves relative to this module's location so it never depends
    on where the process was launched from.
    """
    raw = os.environ.get("EVALOPS_EXPORTS_DIR", "")
    if raw and raw.strip():
        p = Path(raw.strip())
    else:
        # apps/api/app/config.py → parent = apps/api/app → parent = apps/api
        p = Path(__file__).parent.parent / "storage" / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def redis_url() -> str | None:
    raw = os.environ.get("REDIS_URL", "").strip()
    return raw or None


def rate_limit_backend() -> str:
    raw = os.environ.get("EVALOPS_RATE_LIMIT_BACKEND", "auto").strip().lower()
    return raw if raw in ("memory", "redis", "auto") else "auto"


def redis_timeout_ms() -> int:
    return _positive_int("EVALOPS_REDIS_TIMEOUT_MS", 200)


def worker_concurrency() -> int:
    return _positive_int("EVALOPS_WORKER_CONCURRENCY", 4)
