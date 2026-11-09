"""TLS/config and dedicated Redis limits; no SMTP connections."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import ssl
import uuid

import pytest

from app import config
from app.domain.services import rate_limit_service as limits
from app.workers.password_recovery_worker import send_reset_email


@pytest.fixture
def configured(monkeypatch):
    for name, value in {"EVALOPS_SMTP_HOST": "smtp.example.invalid", "EVALOPS_SMTP_FROM": "recovery@example.invalid",
                        "EVALOPS_PUBLIC_ORIGIN": "https://studio.example.invalid", "REDIS_URL": "redis://127.0.0.1:18683/15", "APP_ENV": "production"}.items():
        monkeypatch.setenv(name, value)
    return config.recovery_mail_config()


@pytest.mark.parametrize("field,value", [
    ("EVALOPS_SMTP_HOST", ""), ("EVALOPS_SMTP_FROM", ""), ("REDIS_URL", ""),
    ("EVALOPS_PUBLIC_ORIGIN", "http://studio.example.invalid"),
    ("EVALOPS_PUBLIC_ORIGIN", "https://user:secret@studio.example.invalid"),
    ("EVALOPS_PUBLIC_ORIGIN", "https://studio.example.invalid/path"),
    ("EVALOPS_PUBLIC_ORIGIN", "https://studio.example.invalid/?token=secret"),
    ("EVALOPS_PUBLIC_ORIGIN", "https://studio.example.invalid/#secret"),
    ("EVALOPS_PUBLIC_ORIGIN", "https://studio.example.invalid:invalid"),
    ("EVALOPS_SMTP_FROM", "bad\r\nBcc: other@example.invalid"),
    ("EVALOPS_SMTP_TLS", "none"), ("EVALOPS_SMTP_PORT", "0"), ("EVALOPS_SMTP_PORT", "65536"),
    ("EVALOPS_SMTP_USERNAME", "only-user"),
])
def test_unsafe_config_disables(configured, monkeypatch, field, value):
    assert configured is not None
    monkeypatch.setenv(field, value)
    assert config.recovery_mail_config() is None


@pytest.mark.parametrize("mode", ["starttls", "implicit"])
def test_smtp_verified_tls_timeout_auth_fragment(configured, monkeypatch, mode):
    import smtplib
    calls, messages = [], []
    class SMTP:
        def __init__(self, host, port, **kwargs):
            calls.append((host, port, kwargs))
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def starttls(self, *, context):
            calls.append(context)
        def login(self, username, password):
            calls.append((username, password))
        def send_message(self, message, *, to_addrs):
            assert to_addrs == ["user@example.invalid"]
            messages.append(message)
    monkeypatch.setattr(smtplib, "SMTP", SMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", SMTP)
    cfg = replace(configured, tls=mode, username="test-user", password="test-only-password")
    send_reset_email(cfg, "user@example.invalid", "a" * 43)
    contexts = [c for c in calls if isinstance(c, ssl.SSLContext)]
    if mode == "implicit":
        contexts.append(calls[0][2]["context"])
    assert contexts and all(c.verify_mode == ssl.CERT_REQUIRED and c.check_hostname for c in contexts)
    assert calls[0][2]["timeout"] == 10 and ("test-user", "test-only-password") in calls
    assert "https://studio.example.invalid/reset-password#" + "a" * 43 in messages[0].get_content()
    assert "test-only-password" not in repr(cfg)


def test_dedicated_redis_atomic_independent_private_buckets(monkeypatch):
    target = os.getenv("RECOVERY_TEST_REDIS_URL")
    if not target:
        pytest.skip("requires dedicated Redis")
    assert target == "redis://127.0.0.1:18683/15"
    monkeypatch.setenv("REDIS_URL", target)
    email, ip = uuid.uuid4().hex + "@example.invalid", uuid.uuid4().hex
    with ThreadPoolExecutor(12) as executor:
        results = list(executor.map(lambda _: limits.check_recovery_rate_limits(email, ip), range(12)))
    assert sum(allowed for retry, allowed in results) == 3 and all(retry is None for retry, allowed in results)
    assert limits.check_recovery_rate_limits("other-" + email, ip) == (None, True)
    assert limits.check_recovery_rate_limits(email, "other-" + ip) == (None, False)
    for _ in range(10):
        limits.check_recovery_rate_limits(None, ip)
    assert limits.check_recovery_rate_limits(None, ip)[0] is not None
    client = limits._create_redis_client(target, 1)
    try:
        keys = list(client.scan_iter("evalops:rl:recovery-*"))
        assert keys and all("@" not in key and email not in key for key in keys)
        assert all(0 < client.ttl(key) <= 900 for key in keys)
    finally:
        client.close()


def test_outage_propagates_without_memory_fallback(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:18684/15")
    monkeypatch.setattr(limits._fallback_memory, "check", lambda *_: pytest.fail("memory fallback forbidden"))
    with pytest.raises(Exception):
        limits.check_recovery_rate_limits("unknown@example.invalid", "test-peer")


def test_blocked_ip_does_not_spend_account_quota(monkeypatch):
    target = os.getenv("RECOVERY_TEST_REDIS_URL")
    if not target:
        pytest.skip("requires dedicated Redis")
    assert target == "redis://127.0.0.1:18683/15"
    monkeypatch.setenv("REDIS_URL", target)
    email, blocked, fresh = uuid.uuid4().hex + "@example.invalid", uuid.uuid4().hex, uuid.uuid4().hex
    for _ in range(20):
        assert limits.check_recovery_rate_limits(None, blocked)[0] is None
    for _ in range(3):
        assert limits.check_recovery_rate_limits(email, blocked)[0] is not None
    for _ in range(3):
        assert limits.check_recovery_rate_limits(email, fresh) == (None, True)
    assert limits.check_recovery_rate_limits(email, fresh) == (None, False)


@pytest.mark.parametrize("recipient", ["first,second@example.invalid", "name <second@example.invalid>", "second@example.invalid\r\nBcc: third@example.invalid"])
def test_smtp_rejects_address_lists_or_injected_headers_before_connect(configured, monkeypatch, recipient):
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", lambda *_args, **_kwargs: pytest.fail("must reject before SMTP"))
    with pytest.raises(ValueError):
        send_reset_email(configured, recipient, "a" * 43)
