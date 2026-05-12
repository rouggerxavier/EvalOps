from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Membership, Organization, Project, User


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_register_creates_user_org_and_project_and_returns_session() -> None:
    client = TestClient(app)

    resp = client.post(
        "/v1/auth/register",
        json={
            "email": "Maya@Example.com",
            "name": "Maya Halil",
            "password": "supersecret-12",
            "org_name": "Rogue Labs",
            "project_name": "DocOps Agent",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["token"]
    assert body["user"]["email"] == "maya@example.com"
    assert body["workspace"]["org_slug"] == "rogue-labs"
    assert body["workspace"]["project_slug"] == "docops-agent"

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "maya@example.com").one()
        assert user.password_hash and user.password_hash != "supersecret-12"
        org = db.query(Organization).filter(Organization.slug == "rogue-labs").one()
        membership = (
            db.query(Membership)
            .filter(Membership.user_id == user.id, Membership.organization_id == org.id)
            .one()
        )
        assert membership.role == "owner"
        project = db.query(Project).filter(Project.organization_id == org.id).one()
        assert project.slug == "docops-agent"

    # Token must be usable on /v1/me
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "maya@example.com"


def test_login_with_valid_and_invalid_credentials() -> None:
    client = TestClient(app)
    client.post(
        "/v1/auth/register",
        json={
            "email": "ada@example.com",
            "name": "Ada",
            "password": "lovelace-2026",
        },
    ).raise_for_status()

    ok = client.post(
        "/v1/auth/login",
        json={"email": "ada@example.com", "password": "lovelace-2026"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["token"]
    assert body["workspace"] is not None
    assert body["workspace"]["org_slug"].startswith("ada")

    bad = client.post(
        "/v1/auth/login",
        json={"email": "ada@example.com", "password": "wrong"},
    )
    assert bad.status_code == 401
    assert bad.json()["detail"] == "invalid_credentials"

    missing = client.post(
        "/v1/auth/login",
        json={"email": "nope@example.com", "password": "lovelace-2026"},
    )
    assert missing.status_code == 401


def test_register_rejects_duplicate_email() -> None:
    client = TestClient(app)
    client.post(
        "/v1/auth/register",
        json={"email": "dupe@example.com", "name": "Dupe", "password": "password-123"},
    ).raise_for_status()
    second = client.post(
        "/v1/auth/register",
        json={"email": "dupe@example.com", "name": "Dupe", "password": "password-123"},
    )
    assert second.status_code == 409
    assert second.json()["detail"] == "email_taken"


def test_session_endpoint_returns_workspace() -> None:
    client = TestClient(app)
    reg = client.post(
        "/v1/auth/register",
        json={"email": "session@example.com", "name": "Session", "password": "password-123"},
    ).json()
    s = client.get("/v1/auth/session", headers={"Authorization": f"Bearer {reg['token']}"})
    assert s.status_code == 200
    assert s.json()["user"]["email"] == "session@example.com"
    assert s.json()["workspace"]["project_slug"] == "default-project"
