from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import ApiKey, User
from app.security import create_access_token, verify_api_key


def _auth_header(user_id: str, email: str, name: str) -> dict[str, str]:
    token = create_access_token(sub=user_id, email=email, name=name)
    return {"Authorization": f"Bearer {token}"}


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_phase1_org_project_and_api_key_flow() -> None:
    client = TestClient(app)
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="User One"))
        db.commit()

    headers = _auth_header("usr_1", "u1@example.com", "User One")
    org = client.post("/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"}).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={
            "organization_id": org["id"],
            "name": "Support Agent",
            "slug": "support-agent",
            "description": "Prod assistant",
        },
    ).json()
    create_key_resp = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "production", "environment": "prod", "scopes": ["ingest", "read"]},
    )
    assert create_key_resp.status_code == 201
    body = create_key_resp.json()
    assert body["key"].startswith("evk_prod_")
    assert body["prefix"].startswith("evk_prod_")

    list_resp = client.get(f"/v1/projects/{project['id']}/api-keys", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["data"][0]["id"] == body["id"]

    with SessionLocal() as db:
        key_row = db.get(ApiKey, body["id"])
        assert key_row is not None
        assert key_row.hash != body["key"]
        assert verify_api_key(body["key"], key_row.hash)

    revoke_resp = client.post(f"/v1/projects/{project['id']}/api-keys/{body['id']}/revoke", headers=headers)
    assert revoke_resp.status_code == 204


def test_cross_tenant_access_denied() -> None:
    client = TestClient(app)
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="User One"))
        db.add(User(id="usr_2", email="u2@example.com", name="User Two"))
        db.commit()

    h1 = _auth_header("usr_1", "u1@example.com", "User One")
    h2 = _auth_header("usr_2", "u2@example.com", "User Two")

    org = client.post("/v1/organizations", headers=h1, json={"name": "Acme", "slug": "acme"}).json()
    project = client.post(
        "/v1/projects",
        headers=h1,
        json={"organization_id": org["id"], "name": "P1", "slug": "p1"},
    ).json()

    denied = client.get(f"/v1/projects/{project['id']}/api-keys", headers=h2)
    assert denied.status_code == 404


def _bootstrap_project_with_key(client: TestClient) -> tuple[dict[str, str], str, str]:
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="User One"))
        db.commit()
    headers = _auth_header("usr_1", "u1@example.com", "User One")
    org = client.post("/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"}).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={"organization_id": org["id"], "name": "P1", "slug": "p1"},
    ).json()
    key = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "k1", "environment": "prod", "scopes": ["ingest"]},
    ).json()
    return headers, project["id"], key["id"]


def test_delete_revoked_api_key_removes_row() -> None:
    client = TestClient(app)
    headers, project_id, key_id = _bootstrap_project_with_key(client)

    revoke = client.post(f"/v1/projects/{project_id}/api-keys/{key_id}/revoke", headers=headers)
    assert revoke.status_code == 204

    delete = client.delete(f"/v1/projects/{project_id}/api-keys/{key_id}", headers=headers)
    assert delete.status_code == 204

    listed = client.get(f"/v1/projects/{project_id}/api-keys", headers=headers).json()["data"]
    assert all(row["id"] != key_id for row in listed)
    with SessionLocal() as db:
        assert db.get(ApiKey, key_id) is None


def test_delete_active_api_key_returns_409() -> None:
    client = TestClient(app)
    headers, project_id, key_id = _bootstrap_project_with_key(client)

    delete = client.delete(f"/v1/projects/{project_id}/api-keys/{key_id}", headers=headers)
    assert delete.status_code == 409
    assert delete.json()["detail"] == "api_key_not_revoked"

    with SessionLocal() as db:
        assert db.get(ApiKey, key_id) is not None


def test_delete_missing_api_key_returns_404() -> None:
    client = TestClient(app)
    headers, project_id, _ = _bootstrap_project_with_key(client)

    delete = client.delete(f"/v1/projects/{project_id}/api-keys/key_does_not_exist", headers=headers)
    assert delete.status_code == 404


def test_delete_api_key_cross_tenant_denied() -> None:
    client = TestClient(app)
    headers, project_id, key_id = _bootstrap_project_with_key(client)
    client.post(f"/v1/projects/{project_id}/api-keys/{key_id}/revoke", headers=headers)

    with SessionLocal() as db:
        db.add(User(id="usr_2", email="u2@example.com", name="User Two"))
        db.commit()
    other = _auth_header("usr_2", "u2@example.com", "User Two")

    denied = client.delete(f"/v1/projects/{project_id}/api-keys/{key_id}", headers=other)
    assert denied.status_code == 404
    with SessionLocal() as db:
        assert db.get(ApiKey, key_id) is not None
