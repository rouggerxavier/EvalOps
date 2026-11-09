"""Personal password changes revoke JWT sessions without touching project API keys."""
from concurrent.futures import ThreadPoolExecutor
import os
from threading import Barrier
import uuid

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from app.api import routes_auth
from app.db import Base, SessionLocal, get_db
from app.deps import authenticate_api_key
from app.domain.services import rate_limit_service as limits
from app.main import app
from app.models import ApiKey, User
from app.security import JWT_ALGORITHM, JWT_SECRET, create_session_token, decode_access_token, hash_password, verify_password

OLD_PASSWORD = "old-password-123"
NEW_PASSWORD = "new-password-456"


@pytest.fixture
def account_env(monkeypatch):
    """Optional PG target is guarded and confined to a fresh schema; default stays test SQLite."""
    monkeypatch.setattr(limits, "_backend", limits.InMemoryRateLimiter())
    monkeypatch.setattr(limits, "_fallback_memory", limits.InMemoryRateLimiter())
    target = os.getenv("ACCOUNT_TEST_DATABASE_URL")
    pg_engine = admin_engine = None
    factory = SessionLocal
    if target:
        url = make_url(target)
        assert (url.get_backend_name(), url.host, url.port, url.database, url.username) == (
            "postgresql", "127.0.0.1", 15633, "evalops_account_test", "evalops"
        ), "ACCOUNT_TEST_DATABASE_URL must target the dedicated account test database"
        schema = "account_test_" + uuid.uuid4().hex
        admin_engine = create_engine(target)
        with admin_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        pg_engine = create_engine(target, connect_args={"options": f"-csearch_path={schema}"})
        Base.metadata.create_all(pg_engine)
        factory = sessionmaker(bind=pg_engine, expire_on_commit=False, autoflush=False)

    def test_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = test_db
    client = TestClient(app)
    registered = client.post("/v1/auth/register", json={
        "name": "Conta", "email": "account@example.com", "password": OLD_PASSWORD,
    })
    assert registered.status_code == 201, registered.text
    account = registered.json()
    yield client, factory, account
    app.dependency_overrides.pop(get_db, None)
    client.close()
    if pg_engine:
        pg_engine.dispose()
        with admin_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def change(client, token, **overrides):
    return client.post("/v1/auth/change-password", headers=headers(token), json={
        "current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD, **overrides,
    })


def test_change_revokes_all_sessions_and_legacy_but_keeps_project_key(account_env):
    client, factory, account = account_env
    first = account["token"]
    second = client.post("/v1/auth/login", json={"email": "account@example.com", "password": OLD_PASSWORD}).json()["token"]
    claims = decode_access_token(first)
    assert claims.pop("credential_version") == 0
    legacy = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert client.get("/v1/auth/session", headers=headers(legacy)).status_code == 200
    key = client.post(f'/v1/projects/{account["workspace"]["project_id"]}/api-keys', headers=headers(first),
                      json={"name": "Project", "environment": "prod", "scopes": ["read", "ingest"]}).json()["key"]
    result = change(client, first)
    assert result.status_code == 204, result.text
    assert result.content == b""
    for token in [first, second, legacy]:
        assert client.get("/v1/auth/session", headers=headers(token)).status_code == 401
        assert change(client, token).status_code == 401
    assert client.post("/v1/auth/login", json={"email": "account@example.com", "password": OLD_PASSWORD}).status_code == 401
    fresh = client.post("/v1/auth/login", json={"email": "account@example.com", "password": NEW_PASSWORD})
    assert fresh.status_code == 200
    assert decode_access_token(fresh.json()["token"])["credential_version"] == 1
    assert client.get("/v1/auth/session", headers=headers(fresh.json()["token"])).status_code == 200
    with factory() as db:
        user = db.get(User, account["user"]["id"])
        assert user.credential_version == 1
        assert verify_password(NEW_PASSWORD, user.password_hash)
        assert not verify_password(OLD_PASSWORD, user.password_hash)
        project = authenticate_api_key(Request({"type": "http"}), key, db, "read")
        assert project.id == account["workspace"]["project_id"]
        assert db.query(ApiKey).one().revoked_at is None
    # Even a newly signed version-0 helper token cannot restore revoked sessions.
    stale = create_session_token(sub=account["user"]["id"], email="account@example.com", name="Conta")
    assert client.get("/v1/auth/session", headers=headers(stale)).status_code == 401


@pytest.mark.parametrize("version", [None, True, False, "0", 0.0, -1, 1, [], {}])
def test_version_claim_is_strict_and_matches_database(account_env, version):
    client, _, account = account_env
    claims = decode_access_token(account["token"])
    claims["credential_version"] = version
    token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert client.get("/v1/auth/session", headers=headers(token)).status_code == 401


def test_change_requires_jwt_and_current_password_and_never_trusts_target(account_env):
    client, factory, account = account_env
    assert client.post("/v1/auth/change-password", json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD}).status_code == 401
    assert client.post("/v1/auth/change-password", headers={"X-EvalOps-Key": "evk_prod_fake"}, json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD}).status_code == 401
    with factory() as db:
        other = User(id="other-user", email="other@example.com", name="Other", password_hash=hash_password(OLD_PASSWORD))
        db.add(other)
        db.commit()
    wrong = change(client, account["token"], current_password="incorrect")
    assert wrong.status_code == 400 and wrong.json() == {"detail": "invalid_credentials"}
    assert change(client, account["token"], user_id="other-user", email="other@example.com").status_code == 204
    with factory() as db:
        other = db.get(User, "other-user")
        assert other.credential_version == 0
        assert verify_password(OLD_PASSWORD, other.password_hash)


@pytest.mark.parametrize("password", ["", "1234567", "x" * 257, "😀" * 257])
def test_password_policy_leaves_existing_credentials_intact(account_env, password):
    client, factory, account = account_env
    assert change(client, account["token"], new_password=password).status_code == 422
    with factory() as db:
        user = db.get(User, account["user"]["id"])
        assert user.credential_version == 0 and verify_password(OLD_PASSWORD, user.password_hash)


def test_account_without_password_uses_same_invalid_credentials_error(account_env):
    client, factory, account = account_env
    with factory() as db:
        db.get(User, account["user"]["id"]).password_hash = None
        db.commit()
    result = change(client, account["token"])
    assert result.status_code == 400 and result.json() == {"detail": "invalid_credentials"}


def test_user_limiter_precedes_argon2_and_ignores_forwarded_ip(account_env, monkeypatch):
    client, _, account = account_env
    for attempt in range(5):
        result = client.post("/v1/auth/change-password", headers={**headers(account["token"]), "X-Forwarded-For": f"192.0.2.{attempt}"},
                             json={"current_password": "wrong", "new_password": NEW_PASSWORD})
        assert result.status_code == 400
    verify = routes_auth.verify_password
    monkeypatch.setattr(routes_auth, "verify_password", lambda *_: pytest.fail("blocked attempt reached Argon2"))
    blocked = change(client, account["token"])
    assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
    monkeypatch.setattr(routes_auth, "verify_password", verify)
    # Login has an independent bucket.
    assert client.post("/v1/auth/login", json={"email": "account@example.com", "password": OLD_PASSWORD}).status_code == 200


def test_password_change_limiter_fallback_survives_backend_recovery(monkeypatch):
    class BrokenBackend:
        def check(self, *args, **kwargs):
            raise ConnectionError("unavailable")
    monkeypatch.setattr(limits, "_backend", BrokenBackend())
    monkeypatch.setattr(limits, "_fallback_memory", limits.InMemoryRateLimiter())
    for _ in range(5):
        assert limits.check_password_change_rate_limit("user") is None
    monkeypatch.setattr(limits, "_backend", limits.InMemoryRateLimiter())
    assert limits.check_password_change_rate_limit("user") is not None
    assert limits.check_password_change_rate_limit("different-user") is None


def test_failed_commit_rolls_back_hash_and_version(account_env, monkeypatch):
    client, factory, account = account_env
    with factory() as db:
        user = db.get(User, account["user"]["id"])
        def fail_commit():
            db.flush()
            raise RuntimeError("simulated commit failure")
        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="simulated commit failure"):
            routes_auth.change_password(routes_auth.ChangePasswordRequest(current_password=OLD_PASSWORD, new_password=NEW_PASSWORD), user=user, db=db)
        db.rollback()
    with factory() as db:
        user = db.get(User, account["user"]["id"])
        assert user.credential_version == 0 and verify_password(OLD_PASSWORD, user.password_hash)
    assert client.get("/v1/auth/session", headers=headers(account["token"])).status_code == 200


def test_serializes_changes_with_stale_identity_maps(account_env):
    _, factory, account = account_env
    barrier = Barrier(2)
    def attempt(password):
        with factory() as db:
            user = db.get(User, account["user"]["id"])
            assert user.credential_version == 0
            barrier.wait(timeout=5)
            try:
                response = routes_auth.change_password(routes_auth.ChangePasswordRequest(current_password=OLD_PASSWORD, new_password=password), user=user, db=db)
                return response.status_code, password
            except HTTPException as error:
                db.rollback()
                return error.status_code, password
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["concurrent-password-A", "concurrent-password-B"]))
    assert sorted(code for code, _ in results) == [204, 401]
    winner = next(password for code, password in results if code == 204)
    with factory() as db:
        user = db.get(User, account["user"]["id"])
        assert user.credential_version == 1 and verify_password(winner, user.password_hash)


@pytest.mark.parametrize("password", ["x" * 8, "x" * 256, "😀" * 8, "😀" * 256])
def test_password_policy_accepts_boundaries(account_env, password):
    client, factory, account = account_env
    assert change(client, account["token"], new_password=password).status_code == 204
    with factory() as db:
        assert verify_password(password, db.get(User, account["user"]["id"]).password_hash)


def test_sqlite_compatibility_preserves_existing_users(tmp_path, monkeypatch):
    from app import db as database
    dev_engine = create_engine(f"sqlite:///{tmp_path / 'old-dev.db'}")
    with dev_engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR(64) PRIMARY KEY, password_hash VARCHAR(512))"))
        conn.execute(text("INSERT INTO users (id, password_hash) VALUES ('existing', 'unchanged-hash')"))
    monkeypatch.setattr(database, "engine", dev_engine)
    database.ensure_schema_compatibility()
    database.ensure_schema_compatibility()
    with dev_engine.connect() as conn:
        assert conn.execute(text("SELECT id, password_hash, credential_version FROM users")).one() == ("existing", "unchanged-hash", 0)
    dev_engine.dispose()


@pytest.mark.parametrize("data", [
    {"current_password": OLD_PASSWORD, "new_password": "private-short"[:7]},
    {"current_password": OLD_PASSWORD, "new_password": "private-long-" * 30},
    {"current_password": ["private-current"], "new_password": NEW_PASSWORD},
    "{\"current_password\":\"private-malformed",
])
def test_validation_never_echoes_passwords_in_response_or_logs(account_env, data, caplog):
    client, _, account = account_env
    caplog.set_level("INFO")
    kwargs = {"content": data, "headers": {**headers(account["token"]), "Content-Type": "application/json"}} if isinstance(data, str) else {"json": data, "headers": headers(account["token"])}
    response = client.post("/v1/auth/change-password", **kwargs)
    assert response.status_code == 422
    assert response.json() == {"detail": "invalid_password"}
    assert any(record.name == "evalops.access" for record in caplog.records)
    assert "private-" not in caplog.text and OLD_PASSWORD not in caplog.text and NEW_PASSWORD not in caplog.text


def test_dev_seed_issues_current_version_to_temporary_env_file(account_env, tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    import sys

    client, factory, _ = account_env
    monkeypatch.setattr(sys.stdout, "reconfigure", lambda **_: None, raising=False)
    script = Path(__file__).resolve().parents[1] / "scripts" / "seed_dev.py"
    spec = importlib.util.spec_from_file_location("account_seed_dev", script)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    fake_script = tmp_path / "repo" / "apps" / "api" / "scripts" / "seed_dev.py"
    env_file = tmp_path / "repo" / "apps" / "web" / ".env.local"
    env_file.parent.mkdir(parents=True)
    monkeypatch.setattr(seed, "__file__", str(fake_script))
    monkeypatch.setattr(seed, "SessionLocal", factory)
    with factory() as db:
        monkeypatch.setattr(seed, "engine", db.bind)
        db.add(User(id="dev-existing", email=seed.EMAIL, name="Dev", credential_version=4, password_hash=hash_password(OLD_PASSWORD)))
        db.commit()
    # Schema compatibility has its own temporary SQLite test; do not target any personal dev DB here.
    monkeypatch.setattr(seed, "ensure_schema_compatibility", lambda: None)
    seed.main()
    token = next(line.split("=", 1)[1] for line in env_file.read_text().splitlines() if line.startswith("EVALOPS_DASHBOARD_BEARER_TOKEN="))
    assert decode_access_token(token)["credential_version"] == 4
    assert client.get("/v1/auth/session", headers=headers(token)).status_code == 200
