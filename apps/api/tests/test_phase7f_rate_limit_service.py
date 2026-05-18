"""Phase 7F-A rate limiter abstraction tests."""
from __future__ import annotations

from app.domain.services import rate_limit_service
from app.domain.services.rate_limit_service import (
    InMemoryRateLimiter,
    RateLimitResult,
    api_key_rate_limit_key,
    check_api_key_rate_limit,
    reset_all,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_in_memory_backend_preserves_limit_per_key() -> None:
    clock = _Clock()
    limiter = InMemoryRateLimiter(time_fn=clock)

    assert limiter.check("key-a", 2, 60).allowed is True
    assert limiter.check("key-a", 2, 60).allowed is True

    blocked = limiter.check("key-a", 2, 60)
    assert blocked == RateLimitResult(
        allowed=False,
        remaining=0,
        retry_after_seconds=61,
    )


def test_in_memory_backend_isolates_keys() -> None:
    clock = _Clock()
    limiter = InMemoryRateLimiter(time_fn=clock)

    assert limiter.check("key-a", 1, 60).allowed is True
    assert limiter.check("key-a", 1, 60).allowed is False

    allowed_other_key = limiter.check("key-b", 1, 60)
    assert allowed_other_key.allowed is True
    assert allowed_other_key.remaining == 0


def test_reset_all_preserves_test_seam() -> None:
    reset_all()

    assert check_api_key_rate_limit("apk_test_reset", 1) is None
    assert check_api_key_rate_limit("apk_test_reset", 1) is not None

    reset_all()

    assert check_api_key_rate_limit("apk_test_reset", 1) is None


def test_api_key_limiter_key_uses_non_secret_identifier() -> None:
    raw_api_key = "eok_live_raw_secret_value"
    key_id = "apk_safe_identifier"

    internal_key = api_key_rate_limit_key(key_id)

    assert key_id in internal_key
    assert raw_api_key not in internal_key
    assert internal_key != raw_api_key


def test_facade_delegates_safe_api_key_identifier(monkeypatch) -> None:
    captured_keys: list[str] = []

    class CapturingBackend:
        def check(self, key: str, limit: int, window_seconds: float, *, record: bool = True) -> RateLimitResult:
            captured_keys.append(key)
            return RateLimitResult(allowed=True, remaining=limit - 1)

        def record(self, key: str) -> None:
            captured_keys.append(key)

        def reset(self, key: str | None = None) -> None:
            captured_keys.clear()

    backend = CapturingBackend()
    monkeypatch.setattr(rate_limit_service, "_backend", backend)

    assert check_api_key_rate_limit("apk_capture", 10) is None

    assert captured_keys == ["api-key:apk_capture"]
