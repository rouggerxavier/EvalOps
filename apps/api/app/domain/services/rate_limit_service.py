"""Rate limit facade and in-memory backend for auth-sensitive paths.

The public functions in this module are the compatibility surface used by
``deps.get_project_from_api_key`` and ``routes_auth.login``. Phase 7F-A keeps
the existing single-process sliding-window behavior while moving the storage
behind a small backend interface. Redis/distributed storage is intentionally
left for 7F-B.

Two independent buckets are currently backed by ``InMemoryRateLimiter``:

* ``api_key_hits`` — keyed by ``ApiKey.id``, window 60s, ceiling configurable
  per-key via ``ApiKey.rate_limit_per_minute`` (default 60). The raw API key is
  never used as a limiter key.
* ``login_failures`` — keyed by normalized ``email|ip``, window 300s, ceiling 5.
  Counts *failed* login attempts only; a successful login clears the bucket so
  legitimate users are not punished for past typos.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Protocol

API_KEY_WINDOW_S = 60.0
LOGIN_WINDOW_S = 300.0
LOGIN_MAX_FAILURES = 5
DEFAULT_API_KEY_PER_MINUTE = 60


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int | None = None


class RateLimiterBackend(Protocol):
    def check(
        self,
        key: str,
        limit: int,
        window_seconds: float,
        *,
        record: bool = True,
    ) -> RateLimitResult:
        """Check a bucket and optionally record the current hit."""

    def record(self, key: str) -> None:
        """Record a hit without checking a limit."""

    def reset(self, key: str | None = None) -> None:
        """Clear one bucket or all buckets."""


class InMemoryRateLimiter:
    """Single-process sliding-window backend preserving the Phase 2 behavior."""

    def __init__(self, *, time_fn: Callable[[], float] = time.monotonic) -> None:
        self._time_fn = time_fn
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(
        self,
        key: str,
        limit: int,
        window_seconds: float,
        *,
        record: bool = True,
    ) -> RateLimitResult:
        now = self._time_fn()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._hits[key]
            _trim(bucket, cutoff)
            if len(bucket) >= limit:
                retry = max(1, int(window_seconds - (now - bucket[0])) + 1)
                return RateLimitResult(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=retry,
                )
            if record:
                bucket.append(now)
            remaining = max(0, limit - len(bucket))
            return RateLimitResult(allowed=True, remaining=remaining)

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(self._time_fn())

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


_backend: RateLimiterBackend = InMemoryRateLimiter()

def _trim(bucket: deque[float], cutoff: float) -> None:
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def api_key_rate_limit_key(key_id: str) -> str:
    """Build the internal API-key limiter key from a non-secret ApiKey.id."""
    return f"api-key:{key_id}"


def check_api_key_rate_limit(key_id: str, per_minute: int | None) -> int | None:
    """Record a hit and return ``Retry-After`` seconds when over the cap.

    Returns ``None`` when the call is allowed.
    """
    limit = per_minute if per_minute and per_minute > 0 else DEFAULT_API_KEY_PER_MINUTE
    result = _backend.check(api_key_rate_limit_key(key_id), limit, API_KEY_WINDOW_S)
    return result.retry_after_seconds


def _login_key(email: str, ip: str) -> str:
    return f"login:{email.strip().lower()}|{ip}"


def check_login_rate_limit(email: str, ip: str) -> int | None:
    """Return ``Retry-After`` seconds if the email+ip pair is currently blocked."""
    key = _login_key(email, ip)
    result = _backend.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S, record=False)
    return result.retry_after_seconds


def record_login_failure(email: str, ip: str) -> None:
    key = _login_key(email, ip)
    _backend.record(key)


def reset_login_failures(email: str, ip: str) -> None:
    key = _login_key(email, ip)
    _backend.reset(key)


def reset_all() -> None:
    """Clear all active rate-limit counters. Test-only helper."""
    _backend.reset()
