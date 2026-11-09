"""Rate limit facade and in-memory backend for auth-sensitive paths.

The public functions in this module are the compatibility surface used by
``deps.get_project_from_api_key`` and ``routes_auth.login``. Phase 7F-A keeps
the existing single-process sliding-window behavior while moving the storage
behind a small backend interface. Phase 7F-B adds an optional Redis backend
selected via ``EVALOPS_RATE_LIMIT_BACKEND`` / ``REDIS_URL``.

Two independent buckets share the active backend:

* ``api_key_hits`` — keyed by ``ApiKey.id``, window 60s, ceiling configurable
  per-key via ``ApiKey.rate_limit_per_minute`` (default 60). The raw API key is
  never used as a limiter key.
* ``login_failures`` — keyed by sha256(email|ip), window 300s, ceiling 5.
  Counts *failed* login attempts only; a successful login clears the bucket so
  legitimate users are not punished for past typos.

Outage policy (7F-B, decided before implementation):
  - API-key / ingest limiter: fail-open. If Redis is unavailable, the request
    is allowed and a warning is logged. Auth (key validity, expiry, scopes) is
    still fully enforced upstream; rate limiting is abuse mitigation only.
  - Login limiter: fallback to ``_fallback_memory`` (a second InMemoryRateLimiter)
    for the duration of the outage. Provides partial per-process brute-force
    protection. A warning is logged; no credential or payload is emitted.
"""
from __future__ import annotations

import hashlib
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Protocol

_log = logging.getLogger(__name__)

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


def _fixed_window(window_seconds: float, now: float) -> tuple[int, int]:
    """Return ``(bucket, ttl_seconds)`` for the epoch-aligned fixed window.

    ``bucket = int(now // window_seconds)`` (unchanged 7F-B bucketing).
    ``ttl_seconds`` is whole seconds until the *next* fixed boundary
    ``(bucket + 1) * window_seconds``, floored at 1. This keeps both the Redis
    key TTL and the ``Retry-After`` value aligned to when the bucket actually
    rolls over — not a full window measured from the first hit (P2 fix).
    """
    bucket = int(now // window_seconds)
    next_boundary = (bucket + 1) * window_seconds
    ttl_seconds = max(1, math.ceil(next_boundary - now))
    return bucket, ttl_seconds


class RedisRateLimiter:
    """Fixed-window Redis backend using INCR + EXPIRE (NX).

    Key format: ``evalops:rl:{key}:{window_bucket}`` where
    ``window_bucket = int(time.time() // window_seconds)``.  The key TTL is set
    to the time remaining until the next fixed boundary, so keys self-expire
    exactly when the bucket rolls over; no cleanup job is needed for
    rate-limit keys.

    Trade-off vs InMemoryRateLimiter: fixed window allows up to ~2× the
    configured cap across a window boundary. Documented and accepted for 7F-B.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def _key(self, key: str, bucket: int) -> str:
        return f"evalops:rl:{key}:{bucket}"

    def check(
        self,
        key: str,
        limit: int,
        window_seconds: float,
        *,
        record: bool = True,
    ) -> RateLimitResult:
        bucket, ttl_seconds = _fixed_window(window_seconds, time.time())
        redis_key = self._key(key, bucket)
        if record:
            # INCR then set TTL only on first hit (NX = set-if-no-expiry).
            # TTL is aligned to the next fixed boundary so the key dies exactly
            # when the bucket rolls over. Pipeline is MULTI/EXEC — atomic.
            with self._client.pipeline(True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, ttl_seconds, nx=True)
                results = pipe.execute()
            count = results[0]
            # After INCR, block when count exceeds limit (the request was already counted).
            blocked = count > limit
        else:
            count = int(self._client.get(redis_key) or 0)
            # Read-only check: block when count meets or exceeds limit.
            blocked = count >= limit

        if blocked:
            # Retry-After = seconds until the next fixed boundary, matching the
            # bucket the caller will land in. Not a full window from first hit.
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=ttl_seconds,
            )

        return RateLimitResult(allowed=True, remaining=max(0, limit - count))

    def record(self, key: str) -> None:
        # record() is only used for login failure tracking; uses LOGIN_WINDOW_S
        # so the key bucket matches check(record=False, window_seconds=LOGIN_WINDOW_S).
        bucket, ttl_seconds = _fixed_window(LOGIN_WINDOW_S, time.time())
        redis_key = self._key(key, bucket)
        with self._client.pipeline(True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, ttl_seconds, nx=True)
            pipe.execute()

    def reset(self, key: str | None = None) -> None:
        pattern = f"evalops:rl:{key}:*" if key is not None else "evalops:rl:*"
        cursor = 0
        while True:
            cursor, keys = self._client.scan(cursor, match=pattern, count=100)
            if keys:
                self._client.delete(*keys)
            if cursor == 0:
                break


def _trim(bucket: deque[float], cutoff: float) -> None:
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def api_key_rate_limit_key(key_id: str) -> str:
    """Build the internal API-key limiter key from a non-secret ApiKey.id."""
    return f"api-key:{key_id}"


def _login_key(email: str, ip: str) -> str:
    """Build the internal login limiter key as sha256(email|ip).

    Never stores raw email or IP in Redis keys or in-memory dict keys.
    """
    digest = hashlib.sha256(f"{email.strip().lower()}|{ip}".encode()).hexdigest()
    return f"login:{digest}"


def _create_redis_client(url: str, timeout_s: float) -> Any:
    import redis as _redis_lib

    return _redis_lib.from_url(
        url,
        socket_connect_timeout=timeout_s,
        socket_timeout=timeout_s,
        decode_responses=True,
    )


def _build_backend() -> RateLimiterBackend:
    """Resolve the active backend once from environment config.

    Called at module load time. Lazy import of ``app.config`` avoids circular
    imports at startup; lazy import of ``redis`` avoids breaking environments
    where the package is unavailable (should not happen in production).
    """
    from app import config

    mode = config.rate_limit_backend()
    url = config.redis_url()

    if mode == "memory" or (mode == "auto" and not url):
        return InMemoryRateLimiter()

    if mode == "redis" and not url:
        _log.warning(
            "rate_limit: EVALOPS_RATE_LIMIT_BACKEND=redis but REDIS_URL is unset; "
            "falling back to in-memory"
        )
        return InMemoryRateLimiter()

    # mode == "redis" or mode == "auto" with REDIS_URL present
    try:
        timeout_s = config.redis_timeout_ms() / 1000
        client = _create_redis_client(url, timeout_s)
        return RedisRateLimiter(client)
    except Exception as exc:
        _log.warning(
            "rate_limit: Redis client init failed (%s); falling back to in-memory",
            exc,
        )
        return InMemoryRateLimiter()


_backend: RateLimiterBackend = _build_backend()
_fallback_memory: InMemoryRateLimiter = InMemoryRateLimiter()


def check_api_key_rate_limit(key_id: str, per_minute: int | None) -> int | None:
    """Record a hit and return ``Retry-After`` seconds when over the cap.

    Returns ``None`` when the call is allowed.

    Outage policy: if the configured backend raises (e.g. Redis unavailable),
    fail-open — return ``None`` so ingest continues. A warning is logged
    without the raw API key or any request payload.
    """
    limit = per_minute if per_minute and per_minute > 0 else DEFAULT_API_KEY_PER_MINUTE
    try:
        result = _backend.check(api_key_rate_limit_key(key_id), limit, API_KEY_WINDOW_S)
        return result.retry_after_seconds
    except Exception:
        _log.warning(
            "rate_limit: backend unavailable for API key limiter; failing open"
        )
        return None


def check_login_rate_limit(email: str, ip: str) -> int | None:
    """Return ``Retry-After`` seconds if the email+ip pair is currently blocked.

    Outage policy: if the configured backend raises, fall back to the local
    in-memory limiter. Provides partial per-process brute-force protection.
    A warning is logged without password, token, or raw email.

    Partial-outage fix (P1): even when the backend check succeeds (Redis reads
    work), also consult _fallback_memory. During a write-only outage, failures
    accumulate in the fallback; ignoring it would create a fail-open window.
    """
    key = _login_key(email, ip)
    try:
        result = _backend.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S, record=False)
        if result.allowed:
            fb = _fallback_memory.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S, record=False)
            if not fb.allowed:
                return fb.retry_after_seconds
        return result.retry_after_seconds
    except Exception:
        _log.warning(
            "rate_limit: backend unavailable for login check; using in-memory fallback"
        )
        result = _fallback_memory.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S, record=False)
        return result.retry_after_seconds


def check_password_change_rate_limit(user_id: str) -> int | None:
    """Count every authenticated attempt before password hashing; reuse auth outage fallback."""
    key = f"password_changes:{user_id}"
    fallback = _fallback_memory.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S, record=False)
    if not fallback.allowed:
        return fallback.retry_after_seconds
    try:
        return _backend.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S).retry_after_seconds
    except Exception:
        _log.warning("rate_limit: backend unavailable for password change; using in-memory fallback")
        return _fallback_memory.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S).retry_after_seconds


def record_login_failure(email: str, ip: str) -> None:
    key = _login_key(email, ip)
    try:
        _backend.record(key)
    except Exception:
        _log.warning(
            "rate_limit: backend unavailable for login record; recording locally"
        )
        _fallback_memory.record(key)


def reset_login_failures(email: str, ip: str) -> None:
    key = _login_key(email, ip)
    try:
        _backend.reset(key)
    except Exception:
        pass
    # Always clear the local fallback too — on successful login, any failures
    # recorded during a Redis outage should not carry over.
    _fallback_memory.reset(key)


def reset_all() -> None:
    """Clear all active rate-limit counters. Test-only helper."""
    try:
        _backend.reset()
    except Exception:
        pass
    _fallback_memory.reset()
