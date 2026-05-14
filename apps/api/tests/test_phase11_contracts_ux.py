"""Phase 5 — G-18: real cursor pagination for GET /v1/traces."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, engine, get_db
from app.models import Organization, Project, User, Membership, Trace, utcnow
from app.security import hash_password, create_access_token, new_id

from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TEST_DATABASE_URL = "sqlite:///./test_phase11.db"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True, scope="module")
def setup_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    db = TestSessionLocal()
    user = User(
        id=new_id("usr"),
        email="pagination@test.com",
        name="Pagination User",
        password_hash=hash_password("testpass"),
    )
    org = Organization(id=new_id("org"), name="PaginationOrg", slug="pagination-org")
    project = Project(
        id=new_id("prj"),
        organization_id=org.id,
        name="PaginationProject",
        slug="pagination-project",
    )
    membership = Membership(user_id=user.id, organization_id=org.id, role="owner")
    db.add_all([user, org, project, membership])

    # Create 55 traces with distinct created_at timestamps
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(55):
        t = Trace(
            id=new_id("tr"),
            project_id=project.id,
            organization_id=org.id,
            name=f"trace-{i:03d}",
            service="test-svc",
            environment="prod",
            status="ok",
            started_at=base_time + timedelta(seconds=i),
            ended_at=base_time + timedelta(seconds=i, milliseconds=100),
            duration_ms=100,
            tags={},
            total_tokens_in=10,
            total_tokens_out=5,
            total_cost_usd=0.001,
            redacted=False,
            created_at=base_time + timedelta(seconds=i),
        )
        db.add(t)

    db.commit()
    # Capture IDs before closing session to avoid DetachedInstanceError
    user_id = user.id
    project_id = project.id
    db.close()

    token = create_access_token(sub=user_id, email="pagination@test.com", name="Pagination User")
    return {
        "Authorization": f"Bearer {token}",
        "_project_id": project_id,
    }


def test_first_page_returns_next_cursor_when_more_items(client, auth_headers):
    project_id = auth_headers["_project_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "_project_id"}
    resp = client.get(f"/v1/traces?project_id={project_id}&limit=50", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 50
    assert body["next_cursor"] is not None


def test_second_page_returns_different_items(client, auth_headers):
    project_id = auth_headers["_project_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "_project_id"}

    r1 = client.get(f"/v1/traces?project_id={project_id}&limit=50", headers=headers)
    cursor = r1.json()["next_cursor"]
    first_ids = {t["id"] for t in r1.json()["data"]}

    r2 = client.get(f"/v1/traces?project_id={project_id}&limit=50&cursor={cursor}", headers=headers)
    assert r2.status_code == 200
    second_ids = {t["id"] for t in r2.json()["data"]}

    assert len(second_ids) > 0
    assert first_ids.isdisjoint(second_ids), "Pages must not overlap"


def test_last_page_returns_null_next_cursor(client, auth_headers):
    project_id = auth_headers["_project_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "_project_id"}

    r1 = client.get(f"/v1/traces?project_id={project_id}&limit=50", headers=headers)
    cursor = r1.json()["next_cursor"]

    r2 = client.get(f"/v1/traces?project_id={project_id}&limit=50&cursor={cursor}", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["next_cursor"] is None, "Last page must return null next_cursor"


def test_invalid_cursor_returns_400(client, auth_headers):
    project_id = auth_headers["_project_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "_project_id"}
    resp = client.get(
        f"/v1/traces?project_id={project_id}&cursor=not-valid-base64-!!!", headers=headers
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "invalid_cursor"


def test_soft_deleted_traces_not_in_pagination(client, auth_headers):
    project_id = auth_headers["_project_id"]
    headers = {k: v for k, v in auth_headers.items() if k != "_project_id"}

    # Soft-delete 5 traces directly in DB
    db = TestSessionLocal()
    traces = db.query(Trace).filter(Trace.project_id == project_id).limit(5).all()
    deleted_ids = set()
    for t in traces:
        t.deleted_at = utcnow()
        deleted_ids.add(t.id)
    db.commit()
    db.close()

    # Collect all visible trace IDs across pages
    visible_ids: set[str] = set()
    cursor = None
    while True:
        url = f"/v1/traces?project_id={project_id}&limit=50"
        if cursor:
            url += f"&cursor={cursor}"
        resp = client.get(url, headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        for t in body["data"]:
            visible_ids.add(t["id"])
        cursor = body["next_cursor"]
        if not cursor:
            break

    assert deleted_ids.isdisjoint(visible_ids), "Soft-deleted traces must not appear in pagination"
