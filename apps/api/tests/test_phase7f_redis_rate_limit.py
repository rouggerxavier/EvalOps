"""Phase 7F-B Redis rate limiter backend tests.

Covers:
- Factory/config: memory default when REDIS_URL absent; backend selection by env.
- Redis backend semantics: fixed-window INCR + EXPIRE, independent buckets,
  shared store (multi-worker proof).
- Key safety: raw API key and raw email never appear in Redis keys.
- Outage policy: API key limiter fails open; login limiter falls back to
  in-memory. Warnings emitted; no raw credential logged.
- reset_all() clears both the primary backend and the login fallback.
- Regression: existing tests in test_phase9, test_phase7e, test_phase12 must
  continue to pass (run separately; not duplicated here).

All tests use a fake in-process Redis client — no real Redis server required.
"""
from __future__ import annotations

import fnmatch
import logging
import time
from collections import defaultdict
from typing import Any

import pytest

from app.domain.services import rate_limit_service
from app.domain.services.rate_limit_service import (
    DEFAULT_API_KEY_PER_MINUTE,
    LOGIN_MAX_FAILURES,
    LOGIN_WINDOW_S,
    InMemoryRateLimiter,
    RateLimitResult,
    RedisRateLimiter,
    _build_backend,
    _create_redis_client,
    _login_key,
    api_key_rate_limit_key,
    check_api_key_rate_limit,
    check_login_rate_limit,
    record_login_failure,
    reset_all,
    reset_login_failures,
)


# ---------------------------------------------------------------------------
# Fake Redis client
# ---------------------------------------------------------------------------


class FakeRedis:
    """In-memory Redis fake covering the subset used by RedisRateLimiter."""

    def __init__(self) -> None:
        self._data: dict[str, int] = {}
        self._expiry: dict[str, float] = {}  # absolute wall-clock expiry time

    # -- internal helpers --

    def _prune(self, key: str) -> None:
        if key in self._expiry and time.time() > self._expiry[key]:
            self._data.pop(key, None)
            self._expiry.pop(key, None)

    # -- Redis commands --

    def get(self, key: str) -> str | None:
        self._prune(key)
        val = self._data.get(key)
        return str(val) if val is not None else None

    def incr(self, key: str) -> int:
        self._prune(key)
        val = self._data.get(key, 0) + 1
        self._data[key] = val
        return val

    def expire(self, key: str, seconds: int, *, nx: bool = False, **_: Any) -> bool:
        if nx and key in self._expiry:
            return False
        self._expiry[key] = time.time() + seconds
        return True

    def ttl(self, key: str) -> int:
        self._prune(key)
        if key not in self._expiry:
            return -1
        remaining = self._expiry[key] - time.time()
        return max(0, int(remaining))

    def delete(self, *keys: str) -> int:
        removed = 0
        for k in keys:
            if k in self._data:
                self._data.pop(k)
                self._expiry.pop(k, None)
                removed += 1
        return removed

    def scan(self, cursor: int, *, match: str = "*", count: int = 10) -> tuple[int, list[str]]:
        live = [k for k in self._data if not (k in self._expiry and time.time() > self._expiry[k])]
        matched = [k for k in live if fnmatch.fnmatch(k, match)]
        # Return all in one call (simplified; cursor-0 signals done).
        return 0, matched

    def pipeline(self, transaction: bool = True) -> "_FakePipeline":
        return _FakePipeline(self)

    # -- test helpers --

    def raw_keys(self) -> list[str]:
        """Return all non-expired keys (for assertion)."""
        return [k for k in self._data if not (k in self._expiry and time.time() > self._expiry[k])]


class _FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self._redis = redis
        self._cmds: list[tuple] = []

    def incr(self, key: str) -> "_FakePipeline":
        self._cmds.append(("incr", key))
        return self

    def expire(self, key: str, seconds: int, *, nx: bool = False, **_: Any) -> "_FakePipeline":
        self._cmds.append(("expire", key, seconds, nx))
        return self

    def execute(self) -> list[Any]:
        results = []
        for cmd in self._cmds:
            if cmd[0] == "incr":
                results.append(self._redis.incr(cmd[1]))
            elif cmd[0] == "expire":
                results.append(self._redis.expire(cmd[1], cmd[2], nx=cmd[3]))
        return results

    def __enter__(self) -> "_FakePipeline":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


class BrokenRedis:
    """Redis fake that raises on every operation — simulates full outage."""

    _ERR = ConnectionError("Redis unavailable (test outage)")

    def get(self, key: str) -> None:
        raise self._ERR

    def incr(self, key: str) -> None:
        raise self._ERR

    def expire(self, key: str, seconds: int, **_: Any) -> None:
        raise self._ERR

    def ttl(self, key: str) -> None:
        raise self._ERR

    def delete(self, *keys: str) -> None:
        raise self._ERR

    def scan(self, cursor: int, **_: Any) -> None:
        raise self._ERR

    def pipeline(self, transaction: bool = True) -> "_BrokenPipeline":
        return _BrokenPipeline()


class _BrokenPipeline:
    def incr(self, key: str) -> "_BrokenPipeline":
        return self

    def expire(self, key: str, seconds: int, **_: Any) -> "_BrokenPipeline":
        return self

    def execute(self) -> None:
        raise ConnectionError("Redis unavailable (test outage)")

    def __enter__(self) -> "_BrokenPipeline":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


class _PartialBrokenPipeline:
    """Pipeline where execute() raises — simulates write-only Redis failure."""

    def incr(self, key: str) -> "_PartialBrokenPipeline":
        return self

    def expire(self, key: str, seconds: int, *, nx: bool = False, **_: Any) -> "_PartialBrokenPipeline":
        return self

    def execute(self) -> None:
        raise ConnectionError("Redis write failure (partial outage test)")

    def __enter__(self) -> "_PartialBrokenPipeline":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


class PartialBrokenRedis(FakeRedis):
    """FakeRedis where reads (get/ttl/scan/delete) work but pipeline.execute() fails.

    Models a realistic partial outage: Redis accepts connections and reads but
    write commands (INCR+EXPIRE via pipeline) fail — e.g. replica promoting,
    auth flapping, or network partition on write path.
    """

    def pipeline(self, transaction: bool = True) -> "_PartialBrokenPipeline":
        return _PartialBrokenPipeline()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_backend(fake: FakeRedis | None = None) -> RedisRateLimiter:
    return RedisRateLimiter(fake or FakeRedis())


# ---------------------------------------------------------------------------
# 1. Factory / config
# ---------------------------------------------------------------------------


def test_memory_default_without_redis_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("EVALOPS_RATE_LIMIT_BACKEND", raising=False)
    backend = _build_backend()
    assert isinstance(backend, InMemoryRateLimiter)


def test_memory_mode_env_forces_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("EVALOPS_RATE_LIMIT_BACKEND", "memory")
    backend = _build_backend()
    assert isinstance(backend, InMemoryRateLimiter)


def test_redis_mode_without_url_warns_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("EVALOPS_RATE_LIMIT_BACKEND", "redis")
    with caplog.at_level(logging.WARNING, logger="app.domain.services.rate_limit_service"):
        backend = _build_backend()
    assert isinstance(backend, InMemoryRateLimiter)
    assert any("REDIS_URL" in r.message or "unset" in r.message for r in caplog.records)


def test_auto_mode_with_redis_url_creates_redis_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.delenv("EVALOPS_RATE_LIMIT_BACKEND", raising=False)
    monkeypatch.setattr(rate_limit_service, "_create_redis_client", lambda url, t: fake)
    backend = _build_backend()
    assert isinstance(backend, RedisRateLimiter)


def test_redis_mode_with_url_creates_redis_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("EVALOPS_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(rate_limit_service, "_create_redis_client", lambda url, t: fake)
    backend = _build_backend()
    assert isinstance(backend, RedisRateLimiter)


def test_redis_init_failure_falls_back_to_memory(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://bad-host:9999/0")
    monkeypatch.setenv("EVALOPS_RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(
        rate_limit_service,
        "_create_redis_client",
        lambda url, t: (_ for _ in ()).throw(OSError("connection refused")),
    )
    with caplog.at_level(logging.WARNING, logger="app.domain.services.rate_limit_service"):
        backend = _build_backend()
    assert isinstance(backend, InMemoryRateLimiter)


# ---------------------------------------------------------------------------
# 2. Redis backend: increment and block
# ---------------------------------------------------------------------------


def test_redis_backend_allows_up_to_limit_then_blocks() -> None:
    fake = FakeRedis()
    limiter = _make_redis_backend(fake)
    limit = 3

    for _ in range(limit):
        result = limiter.check("api-key:apk_test", limit, 60.0)
        assert result.allowed is True

    blocked = limiter.check("api-key:apk_test", limit, 60.0)
    assert blocked.allowed is False
    assert blocked.remaining == 0
    assert blocked.retry_after_seconds is not None
    assert blocked.retry_after_seconds >= 1


def test_redis_backend_ttl_is_set_on_first_hit() -> None:
    fake = FakeRedis()
    limiter = _make_redis_backend(fake)

    limiter.check("api-key:apk_ttl", 10, 60.0)

    # At least one key must have a positive TTL (≤ 60 s).
    for key in fake.raw_keys():
        if "apk_ttl" in key:
            ttl = fake.ttl(key)
            assert 0 < ttl <= 60
            break
    else:
        pytest.fail("No key created in FakeRedis for api-key:apk_ttl")


def test_redis_backend_buckets_are_independent() -> None:
    fake = FakeRedis()
    limiter = _make_redis_backend(fake)

    # Fill key-a to limit.
    for _ in range(2):
        limiter.check("api-key:apk_a", 2, 60.0)
    assert limiter.check("api-key:apk_a", 2, 60.0).allowed is False

    # key-b is untouched.
    assert limiter.check("api-key:apk_b", 2, 60.0).allowed is True


def test_redis_backend_two_instances_share_counter() -> None:
    """Two RedisRateLimiter instances sharing the same store respect a single cap.

    This simulates multi-worker behavior (G7F-1/G7F-2).
    """
    fake = FakeRedis()
    worker_a = RedisRateLimiter(fake)
    worker_b = RedisRateLimiter(fake)
    limit = 4

    # 2 hits from each worker = 4 total
    for _ in range(2):
        assert worker_a.check("api-key:apk_shared", limit, 60.0).allowed is True
        assert worker_b.check("api-key:apk_shared", limit, 60.0).allowed is True

    # 5th request (either worker) must be blocked.
    assert worker_a.check("api-key:apk_shared", limit, 60.0).allowed is False


# ---------------------------------------------------------------------------
# 3. Key safety
# ---------------------------------------------------------------------------


def test_redis_api_key_does_not_contain_raw_secret() -> None:
    """The raw API key value (the secret) must never appear in any Redis key."""
    raw_secret = "eok_live_super_secret_value_12345"
    key_id = "apk_safe_identifier_999"

    fake = FakeRedis()
    limiter = _make_redis_backend(fake)
    limiter.check(api_key_rate_limit_key(key_id), 10, 60.0)

    for redis_key in fake.raw_keys():
        assert raw_secret not in redis_key, f"Raw secret found in Redis key: {redis_key!r}"
        assert key_id in redis_key, f"Expected key_id in Redis key: {redis_key!r}"


def test_redis_login_key_does_not_contain_raw_email() -> None:
    """Raw email must not appear in the login limiter key sent to Redis."""
    email = "victim@example.com"
    ip = "192.168.1.1"

    fake = FakeRedis()
    limiter = _make_redis_backend(fake)
    limiter.record(_login_key(email, ip))

    for redis_key in fake.raw_keys():
        assert email not in redis_key, f"Raw email found in Redis key: {redis_key!r}"
        assert email.split("@")[0] not in redis_key


def test_login_key_is_deterministic_and_opaque() -> None:
    email = "user@example.com"
    ip = "10.0.0.1"
    key1 = _login_key(email, ip)
    key2 = _login_key(email, ip)
    assert key1 == key2
    assert email not in key1
    assert ip not in key1
    assert key1.startswith("login:")


# ---------------------------------------------------------------------------
# 4. API key outage → fail-open
# ---------------------------------------------------------------------------


def test_api_key_redis_outage_fails_open(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If Redis raises during API key check, the call is allowed (fail-open)."""
    broken = RedisRateLimiter(BrokenRedis())
    monkeypatch.setattr(rate_limit_service, "_backend", broken)

    with caplog.at_level(logging.WARNING, logger="app.domain.services.rate_limit_service"):
        result = check_api_key_rate_limit("apk_outage_test", 5)

    # fail-open: None means "allowed"
    assert result is None
    assert any("unavailable" in r.message.lower() or "failing open" in r.message for r in caplog.records)


def test_api_key_redis_outage_warning_does_not_leak_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warning log on API key outage must not contain the raw key_id in a way
    that could leak sensitive context (key_id is safe/internal but raw API
    key value is never passed to this function)."""
    broken = RedisRateLimiter(BrokenRedis())
    monkeypatch.setattr(rate_limit_service, "_backend", broken)

    raw_secret = "eok_live_verysecret"
    with caplog.at_level(logging.WARNING):
        check_api_key_rate_limit("apk_safe_id_only", 5)

    for record in caplog.records:
        assert raw_secret not in record.message


# ---------------------------------------------------------------------------
# 5. Login outage → fallback in-memory
# ---------------------------------------------------------------------------


def test_login_redis_outage_falls_back_to_memory(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """If Redis raises during login check/record, fall back to in-memory
    so brute-force protection is partially preserved."""
    broken = RedisRateLimiter(BrokenRedis())
    local_fallback = InMemoryRateLimiter()
    monkeypatch.setattr(rate_limit_service, "_backend", broken)
    monkeypatch.setattr(rate_limit_service, "_fallback_memory", local_fallback)

    email = "attacker@example.com"
    ip = "1.2.3.4"

    with caplog.at_level(logging.WARNING, logger="app.domain.services.rate_limit_service"):
        # Before any failures, login check must be allowed.
        assert check_login_rate_limit(email, ip) is None

        # Record failures up to the limit via the fallback.
        for _ in range(LOGIN_MAX_FAILURES):
            record_login_failure(email, ip)

        # Now login check must be blocked (fallback enforcing the cap).
        blocked = check_login_rate_limit(email, ip)

    assert blocked is not None
    assert blocked >= 1
    assert any("fallback" in r.message.lower() or "unavailable" in r.message.lower() for r in caplog.records)


def test_login_redis_outage_warning_does_not_log_password(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = RedisRateLimiter(BrokenRedis())
    monkeypatch.setattr(rate_limit_service, "_backend", broken)
    monkeypatch.setattr(rate_limit_service, "_fallback_memory", InMemoryRateLimiter())

    password = "S3cr3tP@ssword!"
    with caplog.at_level(logging.WARNING):
        record_login_failure("u@example.com", "10.0.0.1")

    for record in caplog.records:
        assert password not in record.message
        # raw email should not appear either
        assert "u@example.com" not in record.message


# ---------------------------------------------------------------------------
# 6. reset_all clears both backends
# ---------------------------------------------------------------------------


def test_reset_all_clears_primary_backend_state(monkeypatch: pytest.MonkeyPatch) -> None:
    mem = InMemoryRateLimiter()
    monkeypatch.setattr(rate_limit_service, "_backend", mem)
    monkeypatch.setattr(rate_limit_service, "_fallback_memory", InMemoryRateLimiter())

    # Hit until blocked.
    check_api_key_rate_limit("apk_reset_test", 1)
    assert check_api_key_rate_limit("apk_reset_test", 1) is not None

    reset_all()
    assert check_api_key_rate_limit("apk_reset_test", 1) is None


def test_reset_all_clears_fallback_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    fallback = InMemoryRateLimiter()
    monkeypatch.setattr(rate_limit_service, "_backend", RedisRateLimiter(BrokenRedis()))
    monkeypatch.setattr(rate_limit_service, "_fallback_memory", fallback)

    email, ip = "r@example.com", "5.5.5.5"
    for _ in range(LOGIN_MAX_FAILURES):
        record_login_failure(email, ip)  # goes to fallback (Redis broken)

    reset_all()

    # After reset, fallback is clear — check must pass now.
    # Re-inject fallback since monkeypatch restored module attr after reset_all ran.
    monkeypatch.setattr(rate_limit_service, "_fallback_memory", fallback)
    assert check_login_rate_limit(email, ip) is None


# ---------------------------------------------------------------------------
# 7. Redis backend login record + check consistency
# ---------------------------------------------------------------------------


def test_redis_login_record_and_check_use_same_window_bucket() -> None:
    """record() and check(record=False) must refer to the same Redis key."""
    fake = FakeRedis()
    limiter = _make_redis_backend(fake)
    email = "bf@example.com"
    ip = "9.9.9.9"
    key = _login_key(email, ip)

    # Record failures.
    for _ in range(LOGIN_MAX_FAILURES):
        limiter.record(key)

    # check(record=False) must see them and report blocked.
    result = limiter.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S, record=False)
    assert result.allowed is False
    assert result.retry_after_seconds is not None


def test_redis_login_reset_clears_key() -> None:
    fake = FakeRedis()
    limiter = _make_redis_backend(fake)
    key = _login_key("reset@example.com", "1.1.1.1")

    for _ in range(LOGIN_MAX_FAILURES):
        limiter.record(key)

    assert limiter.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S, record=False).allowed is False

    limiter.reset(key)

    assert limiter.check(key, LOGIN_MAX_FAILURES, LOGIN_WINDOW_S, record=False).allowed is True


# ---------------------------------------------------------------------------
# 8. Facade + Redis backend via module-level monkeypatch
# ---------------------------------------------------------------------------


def test_facade_check_api_key_delegates_to_redis_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    redis_backend = _make_redis_backend(fake)
    monkeypatch.setattr(rate_limit_service, "_backend", redis_backend)

    # With limit=2, first two calls succeed, third blocks.
    assert check_api_key_rate_limit("apk_facade", 2) is None
    assert check_api_key_rate_limit("apk_facade", 2) is None
    assert check_api_key_rate_limit("apk_facade", 2) is not None


def test_facade_reset_login_failures_clears_redis_and_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRedis()
    redis_backend = _make_redis_backend(fake)
    local_fallback = InMemoryRateLimiter()
    monkeypatch.setattr(rate_limit_service, "_backend", redis_backend)
    monkeypatch.setattr(rate_limit_service, "_fallback_memory", local_fallback)

    email, ip = "clear@example.com", "2.2.2.2"

    for _ in range(LOGIN_MAX_FAILURES):
        record_login_failure(email, ip)

    assert check_login_rate_limit(email, ip) is not None

    reset_login_failures(email, ip)

    assert check_login_rate_limit(email, ip) is None


# ---------------------------------------------------------------------------
# 8b. P2 — Retry-After must follow the fixed-window boundary, not a full
#     window measured from the first hit.
# ---------------------------------------------------------------------------


def test_redis_retry_after_matches_fixed_window_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First hit lands near the END of a fixed window; the block in the same
    bucket must report Retry-After ≈ time-to-next-boundary (~1 s), not the
    full 60 s window.

    Before the P2 fix: expire() was called with int(window_seconds)=60 and
    retry_after came from the key TTL → blocked.retry_after_seconds ≈ 60 even
    though the bucket rolls over in <1 s. This test asserts == 1, so it would
    fail against the old behavior.
    """
    clock = {"t": 59.2}  # 0.8 s before the boundary, window = 60 s
    monkeypatch.setattr(time, "time", lambda: clock["t"])

    fake = FakeRedis()
    limiter = _make_redis_backend(fake)
    limit = 2
    key = "api-key:apk_boundary"

    # Exhaust the limit inside the same bucket.
    for _ in range(limit):
        assert limiter.check(key, limit, 60.0).allowed is True

    blocked = limiter.check(key, limit, 60.0)
    assert blocked.allowed is False
    assert blocked.remaining == 0
    # next boundary at t=60.0 → ceil(60.0 - 59.2) == 1, never the full window.
    assert blocked.retry_after_seconds == 1
    assert blocked.retry_after_seconds != 60

    # The TTL written to the Redis key is also aligned to the boundary
    # (FakeRedis stores absolute expiry = now + ttl_seconds).
    boundary_keys = [k for k in fake.raw_keys() if "apk_boundary" in k]
    assert boundary_keys, "expected a bucket key in FakeRedis"
    rk = boundary_keys[0]
    applied_ttl = round(fake._expiry[rk] - clock["t"])
    assert applied_ttl == 1, f"expected boundary-aligned TTL=1, got {applied_ttl}"

    # Advance past the boundary into the next fixed window → new bucket key,
    # the limiter allows requests again.
    clock["t"] = 61.0
    assert limiter.check(key, limit, 60.0).allowed is True


# ---------------------------------------------------------------------------
# 9. P1 — partial Redis write outage: fallback consulted on check
# ---------------------------------------------------------------------------


def test_login_partial_redis_write_outage_uses_fallback_on_check(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Partial outage: Redis reads succeed, writes (pipeline.execute) fail.

    record_login_failure() falls back to _fallback_memory (write raises).
    check_login_rate_limit() gets allowed from backend (get returns 0 — nothing
    was written to Redis). Without the P1 fix, that allowed result would be
    returned and the attacker could keep trying. With the fix, the fallback is
    consulted and the login is blocked.
    """
    partial_broken = RedisRateLimiter(PartialBrokenRedis())
    local_fallback = InMemoryRateLimiter()
    monkeypatch.setattr(rate_limit_service, "_backend", partial_broken)
    monkeypatch.setattr(rate_limit_service, "_fallback_memory", local_fallback)

    email = "bf_partial@example.com"
    ip = "3.3.3.4"

    with caplog.at_level(logging.WARNING, logger="app.domain.services.rate_limit_service"):
        # Before any failures: allowed.
        assert check_login_rate_limit(email, ip) is None

        # Each record_login_failure call hits the broken pipeline → exception →
        # falls back to local_fallback.
        for _ in range(LOGIN_MAX_FAILURES):
            record_login_failure(email, ip)

        # Backend check (read-only get) returns allowed because nothing was
        # written to Redis. P1 fix must consult fallback and block.
        blocked = check_login_rate_limit(email, ip)

    assert blocked is not None, (
        "Expected login blocked after partial Redis write outage accumulates "
        f"{LOGIN_MAX_FAILURES} failures in fallback"
    )
    assert blocked >= 1

    # reset_login_failures must clear fallback → subsequent check allowed.
    reset_login_failures(email, ip)
    assert check_login_rate_limit(email, ip) is None
