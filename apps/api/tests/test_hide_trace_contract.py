"""UI hide keeps the existing personal-session DELETE contract."""
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import ApiKey, AuditLog, Membership, Organization, Project, Trace, User
from app.security import create_access_token, generate_api_key, hash_api_key


def test_hide_requires_personal_membership_and_preserves_204_then_404():
    now = datetime.now(timezone.utc)
    key, prefix = generate_api_key("prod")
    with SessionLocal() as db:
        db.add_all([User(id="owner", email="owner@example.test", name="Owner"),
                    User(id="outsider", email="outsider@example.test", name="Outsider"),
                    Organization(id="org", name="Organization", slug="org")])
        db.flush()
        db.add_all([Membership(user_id="owner", organization_id="org", role="owner"),
                    Project(id="project", organization_id="org", name="Project", slug="project")])
        db.flush()
        db.add_all([ApiKey(id="key", project_id="project", prefix=prefix, hash=hash_api_key(key),
                           name="all-scopes", environment="prod", scopes="read,ingest,evaluate"),
                    Trace(id="trace", project_id="project", organization_id="org", name="Run", environment="prod",
                          status="ok", started_at=now, ended_at=now, duration_ms=0)])
        db.commit()

    def personal(user):
        return {"Authorization": f"Bearer {create_access_token(sub=user, email=f'{user}@example.test', name=user)}"}

    with TestClient(app) as client:
        for headers, expected in [({}, 401), ({"X-EvalOps-Key": key}, 401),
                                  ({"Authorization": f"Bearer {key}"}, 401), (personal("outsider"), 404)]:
            assert client.delete("/v1/traces/trace", headers=headers).status_code == expected
            with SessionLocal() as db:
                assert db.get(Trace, "trace").deleted_at is None
                assert db.query(AuditLog).filter(AuditLog.action == "trace.deleted").count() == 0
        headers = personal("owner")
        response = client.delete("/v1/traces/trace", headers=headers)
        assert response.status_code == 204
        assert response.content == b""
        assert client.delete("/v1/traces/trace", headers=headers).status_code == 404
        assert client.get("/v1/traces/trace", headers=headers).status_code == 404
        assert client.get("/v1/traces?project_id=project", headers=headers).json()["data"] == []
    with SessionLocal() as db:
        assert db.get(Trace, "trace").deleted_at is not None
        assert db.query(AuditLog).filter(AuditLog.action == "trace.deleted").count() == 1
