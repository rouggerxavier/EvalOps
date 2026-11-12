"""Fake SMTP and real dedicated Redis; at-most-once worker delivery."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import os
import ssl
import uuid

import pytest

from app import config
from app.domain.services import membership_service as service, rate_limit_service as limits
from app.models import OrganizationInvitation
from app.workers import invitation_worker as worker
from membership_helpers import issue, membership_env


@pytest.mark.parametrize("tls", ["starttls", "implicit"])
def test_smtp_uses_verified_tls_address_timeout_envelope_fragment(membership_env, monkeypatch, tls):
    calls, messages, contexts = [], [], []
    class SMTP:
        def __init__(self, host, port, **kw):
            calls.append((host, port, kw))
            if "context" in kw:
                contexts.append(kw["context"])
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def starttls(self, *, context):
            contexts.append(context)
        def login(self, username, password):
            calls.append((username, password))
        def send_message(self, message, *, to_addrs):
            assert to_addrs == ["recipient@example.invalid"]
            messages.append(message)
    monkeypatch.setattr("smtplib.SMTP", SMTP)
    monkeypatch.setattr("smtplib.SMTP_SSL", SMTP)
    cfg = replace(config.recovery_mail_config(), tls=tls, username="test", password="synthetic")
    worker.send_invitation_email(cfg, "recipient@example.invalid", "a" * 43)
    assert calls[0][2]["timeout"] == 10 and ("test", "synthetic") in calls
    assert contexts and all(c.verify_mode == ssl.CERT_REQUIRED and c.check_hostname for c in contexts)
    message = messages[0]
    assert str(message["From"]) == "invites@example.invalid" and str(message["To"]) == "recipient@example.invalid"
    assert "https://studio.example.invalid/accept-invitation#" + "a" * 43 in message.get_content()


@pytest.mark.parametrize("recipient", ["first,second@example.invalid", "Name <other@example.invalid>", "other@example.invalid\r\nBcc: third@example.invalid"])
def test_recipient_validation_before_connect(membership_env, monkeypatch, recipient):
    monkeypatch.setattr("smtplib.SMTP", lambda *_a, **_kw: pytest.fail("must validate first"))
    with pytest.raises(ValueError):
        worker.send_invitation_email(config.recovery_mail_config(), recipient, "a" * 43)


@pytest.mark.parametrize("condition", ["flag", "config", "expired", "issuer"])
def test_worker_no_delivery_when_unavailable_or_invalid(membership_env, monkeypatch, condition):
    env = membership_env
    invitation = issue(env)
    if condition == "flag":
        monkeypatch.setenv("EVALOPS_INVITATIONS_ENABLED", "false")
    if condition == "config":
        monkeypatch.delenv("EVALOPS_SMTP_HOST")
    with env.factory() as db:
        if condition == "expired":
            db.get(OrganizationInvitation, invitation["id"]).expires_at = datetime.now(timezone.utc)
        if condition == "issuer":
            from app.models import Membership
            db.get(Membership, ("owner", "org")).role = "viewer"
        db.commit()
    worker._dispatch(env.factory, invitation["id"], lambda *_: pytest.fail("no mail"))
    with env.factory() as db:
        row = db.get(OrganizationInvitation, invitation["id"])
        assert row.status == "pending" and row.token_hash is None


@pytest.mark.parametrize("outcome", ["failed", "crash", "accepted", "reissued", "revoked"])
def test_claim_survives_retry_and_late_finalization(membership_env, outcome, caplog):
    env = membership_env
    invitation = issue(env)
    sent = []
    def mailer(cfg, recipient, token):
        sent.append(token)
        if outcome == "failed":
            raise RuntimeError(token)
        if outcome == "crash":
            raise KeyboardInterrupt()
        with env.second_factory() as db:
            if outcome == "accepted":
                service.accept_invitation(db, "recipient", token)
            elif outcome == "revoked":
                service.revoke_invitation(db, "org", "owner", invitation["id"])
            elif outcome == "reissued":
                service.create_invitation(db, "org", "owner", recipient, "viewer")
    if outcome == "crash":
        with pytest.raises(KeyboardInterrupt):
            worker._dispatch(env.factory, invitation["id"], mailer)
    else:
        worker._dispatch(env.factory, invitation["id"], mailer)
    worker._dispatch(env.factory, invitation["id"], lambda *_: pytest.fail("duplicate SMTP"))
    assert len(sent) == 1 and sent[0] not in caplog.text
    expected = {"failed": "failed", "crash": "sending", "accepted": "accepted", "reissued": "revoked", "revoked": "revoked"}[outcome]
    with env.factory() as db:
        row = db.get(OrganizationInvitation, invitation["id"])
        assert row.status == expected
        assert row.token_hash is not None if outcome == "crash" else row.token_hash is None
        if outcome == "reissued":
            assert db.query(OrganizationInvitation).filter_by(status="pending").count() == 1


def test_invitation_redis_atomic_separate_owner_org_quota(monkeypatch):
    target = os.getenv("MEMBERSHIP_TEST_REDIS_URL")
    if not target:
        pytest.skip("requires dedicated R2 Redis")
    assert target == "redis://127.0.0.1:18684/14"
    monkeypatch.setenv("REDIS_URL", target)
    org, owner = "org_" + uuid.uuid4().hex, "usr_" + uuid.uuid4().hex
    with ThreadPoolExecutor(12) as executor:
        result = list(executor.map(lambda _: limits.check_invitation_rate_limit(org, owner), range(12)))
    assert result.count(None) == 10 and all(v is None or 0 < v <= 300 for v in result)
    assert limits.check_invitation_rate_limit(org + "other", owner) is None
    assert limits.check_invitation_rate_limit(org, owner + "other") is None
    client = limits._create_redis_client(target, 1)
    keys = list(client.scan_iter(f"evalops:rl:invitation-issue:{org}*"))
    try:
        assert keys and all(0 < client.ttl(key) <= 300 for key in keys)
    finally:
        # Only this test's UUID buckets, never flush shared databases.
        client.delete(*keys)
        client.close()


def test_invitation_limit_has_no_memory_fallback(monkeypatch):
    class Broken:
        def close(self):
            pass
        def pipeline(self, *_args, **_kwargs):
            raise ConnectionError("synthetic")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:18684/14")
    monkeypatch.setattr(limits, "_create_redis_client", lambda *_: Broken())
    monkeypatch.setattr(limits._fallback_memory, "check", lambda *_: pytest.fail("memory fallback"))
    with pytest.raises(ConnectionError):
        limits.check_invitation_rate_limit("org", "owner")
