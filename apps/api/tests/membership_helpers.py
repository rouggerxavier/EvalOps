"""Disposable R2 databases and fake delivery; no existing development resources."""
import os
from types import SimpleNamespace
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.api import routes_memberships
from app.db import Base, get_db
from app.main import app
from app.models import Membership, Organization, Project, User
from app.security import create_access_token


def pg_target():
    target = os.getenv("MEMBERSHIP_TEST_DATABASE_URL")
    if not target:
        pytest.skip("requires dedicated R2 PG16")
    url = make_url(target)
    assert (url.get_backend_name(), url.host, url.port, url.database, url.username) == (
        "postgresql", "127.0.0.1", 15634, "evalops_membership_test", "evalops"
    ), "MEMBERSHIP_TEST_DATABASE_URL must target dedicated R2 PG16"
    return target


def headers(user_id):
    # Email/role claims are deliberately untrusted by invitation acceptance.
    return {"Authorization": "Bearer " + create_access_token(sub=user_id, email="forged@example.invalid", name=user_id)}


class FakeQueue:
    def __init__(self):
        self.jobs = []
        self.effect = None

    async def ping(self):
        return True

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, args, kwargs))
        if self.effect:
            self.effect(*args)
        return SimpleNamespace(job_id=kwargs["_job_id"])


@pytest.fixture(params=["sqlite", "postgres"])
def membership_env(request, monkeypatch, tmp_path):
    admin = None
    schema = None
    if request.param == "postgres":
        target = pg_target()
        schema = "membership_test_" + uuid.uuid4().hex
        admin = create_engine(target)
        with admin.begin() as conn:
            assert conn.execute(text("SHOW server_version_num")).scalar().startswith("16")
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        options = {"connect_args": {"options": f"-csearch_path={schema}"}}
    else:
        target = "sqlite:///" + str(tmp_path / "memberships.db")
        options = {"connect_args": {"check_same_thread": False, "timeout": 0.1}}
    engine = create_engine(target, poolclass=NullPool, **options)
    second_engine = create_engine(target, poolclass=NullPool, **options)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    second_factory = sessionmaker(bind=second_engine, expire_on_commit=False, autoflush=False)
    with factory() as db:
        for org_id in ("org", "other"):
            db.add(Organization(id=org_id, name=org_id, slug=org_id))
        for user_id in ("owner", "second", "member", "viewer", "unknown", "outsider", "recipient"):
            db.add(User(id=user_id, email=user_id + "@example.invalid", name=user_id))
        db.flush()
        for user_id, role in [("owner", "owner"), ("member", "member"), ("viewer", "viewer"), ("unknown", "legacy")]:
            db.add(Membership(user_id=user_id, organization_id="org", role=role))
        db.add(Membership(user_id="outsider", organization_id="other", role="owner"))
        db.add(Project(id="project", name="Project", slug="project", organization_id="org"))
        db.commit()
    def dependency():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = dependency
    pool = FakeQueue()
    monkeypatch.setattr(app.state, "arq_pool", pool, raising=False)
    monkeypatch.setattr(routes_memberships, "check_invitation_rate_limit", lambda *_: None)
    for key, value in {"EVALOPS_INVITATIONS_ENABLED": "true", "EVALOPS_SMTP_HOST": "smtp.example.invalid",
        "EVALOPS_SMTP_FROM": "invites@example.invalid", "EVALOPS_PUBLIC_ORIGIN": "https://studio.example.invalid",
        "REDIS_URL": "redis://127.0.0.1:18684/14", "APP_ENV": "production"}.items():
        monkeypatch.setenv(key, value)
    client = TestClient(app)
    try:
        yield SimpleNamespace(client=client, factory=factory, second_factory=second_factory, pool=pool,
                              engine=engine, second_engine=second_engine, dialect=request.param)
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        engine.dispose()
        second_engine.dispose()
        if admin:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def issue(env, email="recipient@example.invalid", role="viewer"):
    response = env.client.post("/v1/organizations/org/invitations", headers=headers("owner"), json={"email": email, "role": role})
    assert response.status_code == 202, response.text
    return response.json()


def dispatch(env, invitation_id):
    from app.workers.invitation_worker import _dispatch
    messages = []
    _dispatch(env.factory, invitation_id, lambda cfg, recipient, token: messages.append((recipient, token)))
    assert len(messages) == 1
    return messages[0][1]
