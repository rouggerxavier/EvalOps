"""Recovery contracts and PG16 serialization. No real SMTP."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from threading import Barrier

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from test_change_password import account_env, headers, OLD_PASSWORD, NEW_PASSWORD
from app.api import routes_auth
from app.db import Base
from app.domain.services import password_recovery as recovery, rate_limit_service as limits
from app.maintenance.cleanup import cleanup_expired_password_resets
from app.models import PasswordReset, User
from app.security import verify_password
from app.workers import password_recovery_worker as worker


class Pool:
    def __init__(self):
        self.jobs = []
        self.down = False

    async def ping(self):
        if self.down:
            raise RuntimeError("sensitive Redis error")
        return True

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, args, kwargs))
        return object()


@pytest.fixture
def recovery_env(account_env, monkeypatch):
    client, factory, account = account_env
    for key, value in {
        "EVALOPS_SMTP_HOST": "smtp.example.invalid", "EVALOPS_SMTP_FROM": "account@example.invalid",
        "EVALOPS_PUBLIC_ORIGIN": "https://studio.example.invalid", "REDIS_URL": "redis://127.0.0.1:18683/15", "APP_ENV": "test",
    }.items():
        monkeypatch.setenv(key, value)
    pool, sent = Pool(), []
    monkeypatch.setattr(client.app.state, "arq_pool", pool, raising=False)
    monkeypatch.setattr(limits, "check_recovery_rate_limits", lambda email, ip: (None, True))
    def mailer(cfg, recipient, token):
        sent.append((cfg.public_origin + "/reset-password#" + token, recipient, token))
    return client, factory, account, pool, sent, mailer


def request_link(env, email="account@example.com"):
    client, factory, _, pool, sent, mailer = env
    result = client.post("/v1/auth/forgot-password", json={"email": email})
    assert result.status_code == 202 and result.content == b""
    name, args, kwargs = pool.jobs[-1]
    assert name == "send_password_reset_job"
    worker._dispatch(factory, *args, mailer)
    return sent[-1][2] if sent else None


def reset(client, token, password=NEW_PASSWORD):
    return client.post("/v1/auth/reset-password", json={"token": token, "new_password": password})


def test_enumeration_job_shape_hash_only_exact_ttl_and_no_logs(recovery_env, caplog):
    client, factory, account, pool, sent, mailer = recovery_env
    with factory() as db:
        db.add(User(id="nohash", email="nohash@example.com", name="No password"))
        db.commit()
    bodies = []
    for email in ["account@example.com", "missing@example.com", "nohash@example.com"]:
        result = client.post("/v1/auth/forgot-password", json={"email": email})
        bodies.append((result.status_code, result.content))
        name, args, kwargs = pool.jobs[-1]
        assert len(args) == 4 and type(args[1]) is int and "@" not in json.dumps(pool.jobs)
        assert kwargs == {"_job_id": args[2], "_expires": 1800}
        asyncio.run(worker.send_password_reset_job({"db_session_factory": factory, "recovery_mailer": mailer}, *args))
    assert bodies == [(202, b"")] * 3 and len(sent) == 1
    token = sent[0][2]
    with factory() as db:
        row = db.query(PasswordReset).one()
        assert row.user_id == account["user"]["id"] and row.token_hash == recovery.token_digest(token) != token
        assert row.status == "sent" and row.expires_at - row.created_at == timedelta(minutes=30)
    assert token not in json.dumps(pool.jobs) + caplog.text and "account@example.com" not in caplog.text


def test_reset_revokes_sessions_requires_new_login_and_cannot_replay(recovery_env):
    client, factory, account, *_ = recovery_env
    token = request_link(recovery_env)
    assert reset(client, token).status_code == 204
    assert client.get("/v1/auth/session", headers=headers(account["token"])).status_code == 401
    for password, status in [(NEW_PASSWORD, 200), (OLD_PASSWORD, 401)]:
        assert client.post("/v1/auth/login", json={"email": "account@example.com", "password": password}).status_code == status
    assert reset(client, token).json() == {"detail": "invalid_reset"}
    with factory() as db:
        assert db.query(PasswordReset).count() == 0 and db.get(User, account["user"]["id"]).credential_version == 1


def test_unknown_tampered_expired_consumed_uniform_and_exact_expiry(recovery_env):
    client, factory, *_ = recovery_env
    token = request_link(recovery_env)
    results = [reset(client, "a" * 43), reset(client, ("b" if token[0] != "b" else "c") + token[1:])]
    with factory() as db:
        row = db.query(PasswordReset).one()
        assert recovery.consume_reset(db, token, NEW_PASSWORD, now=row.expires_at) is False
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    results.append(reset(client, token))
    token = request_link(recovery_env)
    assert reset(client, token).status_code == 204
    results.append(reset(client, token))
    assert [(r.status_code, r.json()) for r in results] == [(400, {"detail": "invalid_reset"})] * 4


@pytest.mark.parametrize("password", ["short", "😀" * 257, "x" * 257, None, 12])
def test_validation_never_echoes_inputs_even_root_path(recovery_env, password):
    client, _, _, *_ = recovery_env
    token = request_link(recovery_env)
    result = reset(client, token, password)
    assert result.status_code == 422 and result.json() == {"detail": "invalid_password"} and token not in result.text
    from fastapi.testclient import TestClient
    nested = TestClient(client.app, root_path="/proxy")
    result = nested.post("/v1/auth/reset-password", json={"token": token, "new_password": password})
    assert result.status_code == 422 and token not in result.text
    nested.close()


@pytest.mark.parametrize("count", [8, 256])
def test_unicode_codepoints(recovery_env, count):
    client, factory, account, *_ = recovery_env
    assert reset(client, request_link(recovery_env), "😀" * count).status_code == 204
    with factory() as db:
        assert verify_password("😀" * count, db.get(User, account["user"]["id"]).password_hash)


def test_new_request_invalidates_old_duplicate_does_not_extend(recovery_env):
    client, factory, _, pool, sent, mailer = recovery_env
    first = request_link(recovery_env)
    args = pool.jobs[-1][1]
    with factory() as db:
        expiry = db.query(PasswordReset).one().expires_at
    worker._dispatch(factory, *args, mailer)
    assert len(sent) == 1
    with factory() as db:
        assert db.query(PasswordReset).one().expires_at == expiry
    second = request_link(recovery_env)
    worker._dispatch(factory, *args, mailer)
    assert len(sent) == 2 and first != second
    assert reset(client, first).status_code == 400 and reset(client, second).status_code == 204


def test_old_version_and_expired_pending_jobs_never_send(recovery_env):
    client, factory, account, pool, sent, mailer = recovery_env
    for change_version in [False, True]:
        assert client.post("/v1/auth/forgot-password", json={"email": "account@example.com"}).status_code == 202
        with factory() as db:
            if change_version:
                db.get(User, account["user"]["id"]).credential_version += 1
            else:
                db.query(PasswordReset).one().expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        worker._dispatch(factory, *pool.jobs[-1][1], mailer)
    assert sent == []


def test_crash_after_claim_never_regenerates(recovery_env):
    client, factory, _, pool, sent, mailer = recovery_env
    assert client.post("/v1/auth/forgot-password", json={"email": "account@example.com"}).status_code == 202
    args = pool.jobs[-1][1]
    def crash(*_):
        raise SystemExit("simulated crash")
    with pytest.raises(SystemExit):
        worker._dispatch(factory, *args, crash)
    with factory() as db:
        row = db.query(PasswordReset).one()
        assert row.status == "sending" and row.token_hash
        digest, expiry = row.token_hash, row.expires_at
    worker._dispatch(factory, *args, mailer)
    assert sent == []
    with factory() as db:
        row = db.query(PasswordReset).one()
        assert (row.token_hash, row.expires_at) == (digest, expiry)


def test_sqlite_concurrent_dispatch_claim_sends_only_once(recovery_env, tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'dispatch.db'}", connect_args={"check_same_thread": False})
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    Base.metadata.create_all(engine)
    moment = datetime.now(timezone.utc)
    with factory() as db:
        db.add(User(id="dispatch-user", email="dispatch@example.invalid", name="Dispatch", password_hash="nonempty"))
        db.commit()
        version = recovery.prepare_request(db, "dispatch-user", "dispatch-request", moment)
    gate, generated, sent = Barrier(2), [], []
    original = worker.secrets.token_urlsafe
    def concurrent_token(size):
        gate.wait(timeout=10)
        token = original(size)
        generated.append(token)
        return token
    monkeypatch.setattr(worker.secrets, "token_urlsafe", concurrent_token)
    try:
        with ThreadPoolExecutor(2) as executor:
            futures = [executor.submit(worker._dispatch, factory, "dispatch-user", version,
                        "dispatch-request", moment.isoformat(), lambda cfg, recipient, token: sent.append(token)) for _ in range(2)]
            for future in futures:
                future.result(timeout=15)
        assert len(generated) == 2 and len(sent) == 1
        with factory() as db:
            row = db.query(PasswordReset).one()
            assert row.status == "sent" and row.token_hash == recovery.token_digest(sent[0])
    finally:
        engine.dispose()


def test_pg_worker_accepts_same_instant_in_non_utc_session(recovery_env):
    client, factory, _, pool, sent, mailer = recovery_env
    source = factory.kw["bind"]
    if source.dialect.name != "postgresql":
        pytest.skip("requires dedicated PG16")
    assert client.post("/v1/auth/forgot-password", json={"email": "account@example.com"}).status_code == 202
    with factory() as db:
        schema = db.execute(text("SELECT current_schema()")).scalar_one()
    assert schema.startswith("account_test_")
    engine = create_engine(source.url, connect_args={"options": f"-csearch_path={schema} -ctimezone=America/Fortaleza"})
    local_factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    try:
        with local_factory() as db:
            stored = db.query(PasswordReset).one().requested_at
            assert stored.utcoffset() == timedelta(hours=-3)
            assert stored == datetime.fromisoformat(pool.jobs[-1][1][3])
        worker._dispatch(local_factory, *pool.jobs[-1][1], mailer)
        assert len(sent) == 1
        assert reset(client, sent[0][2]).status_code == 204
    finally:
        engine.dispose()


def test_smtp_failure_invalidates_only_its_token_safe_logs(recovery_env, caplog):
    client, factory, _, pool, sent, mailer = recovery_env
    assert client.post("/v1/auth/forgot-password", json={"email": "account@example.com"}).status_code == 202
    raw = []
    def fail(cfg, recipient, token):
        raw.append(token)
        raise RuntimeError(f"SMTP secret {recipient} {token} {cfg.public_origin}")
    worker._dispatch(factory, *pool.jobs[-1][1], fail)
    with factory() as db:
        assert db.query(PasswordReset).one().status == "failed" and db.query(PasswordReset).one().token_hash is None
    assert reset(client, raw[0]).status_code == 400 and "smtp_failed" in caplog.text
    assert all(secret not in caplog.text for secret in [raw[0], "account@example.com", "SMTP secret", "https://"])
    assert client.post("/v1/auth/forgot-password", json={"email": "account@example.com"}).status_code == 202
    def fail_after_replacement(cfg, recipient, token):
        request_link(recovery_env)
        raise RuntimeError(token)
    worker._dispatch(factory, *pool.jobs[-1][1], fail_after_replacement)
    assert reset(client, sent[-1][2]).status_code == 204


def test_change_removes_recovery_atomically(recovery_env):
    client, factory, account, *_ = recovery_env
    token = request_link(recovery_env)
    result = client.post("/v1/auth/change-password", headers=headers(account["token"]), json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD})
    assert result.status_code == 204 and reset(client, token).status_code == 400
    with factory() as db:
        assert db.query(PasswordReset).count() == 0


def test_rollback_preserves_password_version_and_reset(recovery_env, monkeypatch):
    _, factory, account, *_ = recovery_env
    token = request_link(recovery_env)
    with factory() as db:
        def fail():
            raise RuntimeError("commit failed")
        monkeypatch.setattr(db, "commit", fail)
        with pytest.raises(RuntimeError, match="commit failed"):
            recovery.consume_reset(db, token, NEW_PASSWORD)
        db.rollback()
    with factory() as db:
        user = db.get(User, account["user"]["id"])
        assert user.credential_version == 0 and verify_password(OLD_PASSWORD, user.password_hash)
        assert db.query(PasswordReset).one().token_hash == recovery.token_digest(token)


def test_cleanup_dry_run_and_idempotence(recovery_env):
    _, factory, *_ = recovery_env
    request_link(recovery_env)
    with factory() as db:
        expiry = db.query(PasswordReset).one().expires_at
        assert cleanup_expired_password_resets(db, now=expiry).deleted_rows == 1
        assert db.query(PasswordReset).count() == 1
        assert cleanup_expired_password_resets(db, now=expiry, dry_run=False).deleted_rows == 1
        assert cleanup_expired_password_resets(db, now=expiry, dry_run=False).deleted_rows == 0


def test_global_dependency_failure_precedes_lookup_uniformly(recovery_env, monkeypatch):
    client, factory, _, pool, *_ = recovery_env
    with factory() as db:
        monkeypatch.setattr(db, "query", lambda *_: pytest.fail("lookup before readiness"))
        for unavailable in ["config", "queue", "limiter"]:
            with monkeypatch.context() as patch:
                if unavailable == "config":
                    patch.delenv("EVALOPS_SMTP_HOST")
                elif unavailable == "queue":
                    patch.setattr(pool, "down", True)
                else:
                    def fail(*_):
                        raise RuntimeError("secret")
                    patch.setattr(limits, "check_recovery_rate_limits", fail)
                for email in ["account@example.com", "missing@example.com"]:
                    with pytest.raises(HTTPException) as exc:
                        asyncio.run(routes_auth.forgot_password(routes_auth.ForgotPasswordRequest(email=email), Request({"type": "http", "app": client.app}), db))
                    assert (exc.value.status_code, exc.value.detail) == (503, "recovery_unavailable")


def test_suppression202_ip429_and_forwarded_headers_ignored(recovery_env, monkeypatch):
    client, _, _, pool, *_ = recovery_env
    peers = []
    monkeypatch.setattr(limits, "check_recovery_rate_limits", lambda email, ip: (peers.append((email, ip)) or (None, False)))
    for ip in ["203.0.113.1", "198.51.100.1"]:
        assert client.post("/v1/auth/forgot-password", json={"email": "Account@Example.COM"}, headers={"X-Forwarded-For": ip, "Forwarded": f"for={ip}", "X-Real-IP": ip}).status_code == 202
    assert peers == [("account@example.com", "testclient")] * 2 and pool.jobs == []
    monkeypatch.setattr(limits, "check_recovery_rate_limits", lambda *_: (45, True))
    result = client.post("/v1/auth/forgot-password", json={"email": "missing@example.com"})
    assert result.status_code == 429 and result.headers["Retry-After"] == "45"


def test_pg16_concurrent_reset_and_reset_vs_change(recovery_env):
    _, factory, account, *_ = recovery_env
    if factory.kw["bind"].dialect.name != "postgresql":
        pytest.skip("requires dedicated PG16")
    token = request_link(recovery_env)
    gate = Barrier(2)
    def attempt():
        with factory() as db:
            gate.wait(timeout=10)
            return recovery.consume_reset(db, token, NEW_PASSWORD)
    with ThreadPoolExecutor(2) as executor:
        assert sorted(executor.map(lambda _: attempt(), range(2))) == [False, True]
    # New version/new request races with the authenticated password change at that version.
    token = request_link(recovery_env)
    gate = Barrier(2)
    def do_reset():
        with factory() as db:
            gate.wait(timeout=10)
            return recovery.consume_reset(db, token, OLD_PASSWORD)
    def do_change():
        with factory() as db:
            user = db.get(User, account["user"]["id"])
            gate.wait(timeout=10)
            try:
                return routes_auth.change_password(routes_auth.ChangePasswordRequest(current_password=NEW_PASSWORD, new_password="different-password"), user, db).status_code
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(2) as executor:
        first, second = executor.submit(do_reset), executor.submit(do_change)
        assert (first.result(), second.result()) in [(True, 401), (False, 204)]
    with factory() as db:
        assert db.get(User, account["user"]["id"]).credential_version == 2 and db.query(PasswordReset).count() == 0


@pytest.mark.parametrize("token", [None, "", "bad", "x" * 44, "@" * 43])
def test_malformed_token_is_same_invalid_reset_without_echo(recovery_env, token):
    client, *_ = recovery_env
    result = reset(client, token)
    assert result.status_code == 400 and result.json() == {"detail": "invalid_reset"}


def test_real_arq_job_contains_only_opaque_args_and_worker_sends_fake_mail(recovery_env, caplog):
    import os
    import uuid
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker
    target = os.getenv("RECOVERY_TEST_REDIS_URL")
    if not target:
        pytest.skip("requires dedicated Redis")
    assert target == "redis://127.0.0.1:18683/15"
    client, factory, _, fake_pool, sent, mailer = recovery_env
    assert client.post("/v1/auth/forgot-password", json={"email": "account@example.com"}).status_code == 202
    _, args, _ = fake_pool.jobs[-1]
    async def scenario():
        pool = await create_pool(RedisSettings.from_dsn(target))
        queue_name = "recovery-test-" + uuid.uuid4().hex
        job = await pool.enqueue_job("send_password_reset_job", *args, _queue_name=queue_name, _job_id=args[2], _expires=1800)
        info = await job.info()
        assert info.args == args and info.kwargs == {}
        body = await pool.get("arq:job:" + job.job_id)
        assert b"@" not in body
        arq_worker = Worker([worker.send_password_reset_job], redis_pool=pool, queue_name=queue_name, burst=True,
                            handle_signals=False, poll_delay=0.01, keep_result=0,
                            ctx={"db_session_factory": factory, "recovery_mailer": mailer})
        try:
            await arq_worker.async_run()
            assert arq_worker.jobs_complete == 1 and arq_worker.jobs_failed == 0
        finally:
            await arq_worker.close()
    asyncio.run(scenario())
    assert len(sent) == 1 and sent[0][2] not in caplog.text
