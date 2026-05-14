"""In-memory rate limiters for Phase 2 (G-01, G-13).

Single-process sliding-window counters. Suitable for the MVP single-worker
deployment described in the roadmap; **not** safe across multiple
workers/processes because state lives in the per-process heap and is lost
on restart. Migration to Redis is scheduled for Phase 7.

Two independent buckets:

* ``api_key_hits`` — keyed by ``ApiKey.id``, window 60s, ceiling configurable
  per-key via ``ApiKey.rate_limit_per_minute`` (default 60). Used by
  ``deps.get_project_from_api_key``.
* ``login_failures`` — keyed by ``email|ip``, window 300s, ceiling 5. Counts
  *failed* login attempts only; a successful login clears the bucket so
  legitimate users are not punished for past typos.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

API_KEY_WINDOW_S = 60.0
LOGIN_WINDOW_S = 300.0
LOGIN_MAX_FAILURES = 5
DEFAULT_API_KEY_PER_MINUTE = 60

_api_key_hits: dict[str, deque[float]] = defaultdict(deque)
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_lock = Lock()


def _trim(bucket: deque[float], cutoff: float) -> None:
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def check_api_key_rate_limit(key_id: str, per_minute: int | None) -> int | None:
    """Record a hit and return ``Retry-After`` seconds when over the cap.

    Returns ``None`` when the call is allowed.
    """
    limit = per_minute if per_minute and per_minute > 0 else DEFAULT_API_KEY_PER_MINUTE
    now = time.monotonic()
    cutoff = now - API_KEY_WINDOW_S
    with _lock:
        bucket = _api_key_hits[key_id]
        _trim(bucket, cutoff)
        if len(bucket) >= limit:
            retry = max(1, int(API_KEY_WINDOW_S - (now - bucket[0])) + 1)
            return retry
        bucket.append(now)
        return None


def _login_key(email: str, ip: str) -> str:
    return f"{email.strip().lower()}|{ip}"


def check_login_rate_limit(email: str, ip: str) -> int | None:
    """Return ``Retry-After`` seconds if the email+ip pair is currently blocked."""
    now = time.monotonic()
    cutoff = now - LOGIN_WINDOW_S
    key = _login_key(email, ip)
    with _lock:
        bucket = _login_failures[key]
        _trim(bucket, cutoff)
        if len(bucket) >= LOGIN_MAX_FAILURES:
            retry = max(1, int(LOGIN_WINDOW_S - (now - bucket[0])) + 1)
            return retry
        return None


def record_login_failure(email: str, ip: str) -> None:
    now = time.monotonic()
    key = _login_key(email, ip)
    with _lock:
        _login_failures[key].append(now)


def reset_login_failures(email: str, ip: str) -> None:
    key = _login_key(email, ip)
    with _lock:
        _login_failures.pop(key, None)


def reset_all() -> None:
    """Clear all in-memory counters. Test-only helper."""
    with _lock:
        _api_key_hits.clear()
        _login_failures.clear()
