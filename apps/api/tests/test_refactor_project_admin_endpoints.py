from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import EvaluationRun, Membership, Rubric, User
from app.security import create_access_token


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _auth_header(user_id: str = "usr_1") -> dict[str, str]:
    token = create_access_token(sub=user_id, email=f"{user_id}@example.com", name=f"User {user_id}")
    return {"Authorization": f"Bearer {token}"}


def _bootstrap(client: TestClient) -> tuple[dict[str, str], str, str, str]:
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u1@example.com", name="User One"))
        db.add(User(id="usr_2", email="u2@example.com", name="User Two"))
        db.commit()
    headers = _auth_header()
    org = client.post("/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"}).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={
            "organization_id": org["id"],
            "name": "DocOps",
            "slug": "docops",
            "description": "Original description",
            "default_environment": "prod",
        },
    ).json()
    key = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()["key"]
    return headers, org["id"], project["id"], key


def _ingest_trace(client: TestClient, api_key: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "traces": [
            {
                "client_trace_id": "score-trace",
                "name": "agent.answer",
                "service": "support-agent",
                "environment": "prod",
                "started_at": now.isoformat(),
                "ended_at": (now + timedelta(milliseconds=300)).isoformat(),
                "status": "ok",
                "tags": {},
                "metadata": {},
                "spans": [],
            }
        ]
    }
    response = client.post("/v1/traces", headers={"X-EvalOps-Key": api_key}, json=payload)
    assert response.status_code == 202, response.text
    return response.json()["results"][0]["trace_id"]


def test_patch_project_updates_environment_without_clearing_description() -> None:
    client = TestClient(app)
    headers, _, project_id, _ = _bootstrap(client)

    response = client.patch(
        f"/v1/projects/{project_id}",
        headers=headers,
        json={"name": "DocOps Prod", "default_environment": "staging"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "DocOps Prod"
    assert body["default_environment"] == "staging"
    assert body["description"] == "Original description"


def test_list_organization_members_returns_user_identity_and_role() -> None:
    client = TestClient(app)
    headers, org_id, _, _ = _bootstrap(client)
    with SessionLocal() as db:
        db.add(Membership(user_id="usr_2", organization_id=org_id, role="member"))
        db.commit()

    response = client.get(f"/v1/organizations/{org_id}/members", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [row["email"] for row in data] == ["u1@example.com", "u2@example.com"]
    assert data[0]["role"] == "owner"
    assert data[1]["role"] == "member"
    assert data[1]["name"] == "User Two"


def test_trace_listing_includes_latest_evaluation_score() -> None:
    client = TestClient(app)
    headers, _, project_id, api_key = _bootstrap(client)
    trace_id = _ingest_trace(client, api_key)

    with SessionLocal() as db:
        rubric = Rubric(
            id="rb_last_score",
            project_id=project_id,
            slug="quality",
            description=None,
            current_version=2,
            threshold=0.7,
        )
        db.add(rubric)
        db.add_all(
            [
                EvaluationRun(
                    id="evr_old",
                    project_id=project_id,
                    trace_id=trace_id,
                    rubric_id=rubric.id,
                    rubric_version=1,
                    triggered_by="test",
                    status="completed",
                    aggregate_score=0.4,
                    passed=False,
                    cost_usd=0,
                    run_metadata={},
                    created_at=datetime.now(timezone.utc) - timedelta(hours=1),
                ),
                EvaluationRun(
                    id="evr_new",
                    project_id=project_id,
                    trace_id=trace_id,
                    rubric_id=rubric.id,
                    rubric_version=2,
                    triggered_by="test",
                    status="completed",
                    aggregate_score=0.87,
                    passed=True,
                    cost_usd=0,
                    run_metadata={},
                    created_at=datetime.now(timezone.utc),
                ),
            ]
        )
        db.commit()

    response = client.get(f"/v1/traces?project_id={project_id}", headers=headers)
    assert response.status_code == 200, response.text
    row = response.json()["data"][0]
    assert row["id"] == trace_id
    assert row["last_score"] == 0.87
