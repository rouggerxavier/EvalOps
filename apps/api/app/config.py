"""Runtime configuration sourced from environment variables.

Lazy getters so tests can mutate ``os.environ`` between calls without
re-importing the module.
"""
from __future__ import annotations

import os

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
