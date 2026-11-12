"""Owner invariants, atomic transfer, resource isolation and independent API keys."""
import pytest
from sqlalchemy import event, select

from app.db import Base
from app.deps import authenticate_api_key
from app.models import ApiKey, AuditLog, Membership, Organization, OrganizationInvitation, User
from app.security import generate_api_key, hash_api_key
from starlette.requests import Request
from membership_helpers import dispatch, headers, issue, membership_env

ADMIN_ROUTES = [
    ("POST", "/invitations", {"email": "recipient@example.invalid"}),
    ("GET", "/invitations", None),
    ("POST", "/invitations/missing/revoke", {}),
    ("PATCH", "/members/viewer", {"role": "member"}),
    ("DELETE", "/members/viewer", None),
    ("POST", "/ownership/transfer", {"user_id": "viewer"}),
]


@pytest.mark.parametrize("actor,code", [("member", 403), ("viewer", 403), ("unknown", 403), ("outsider", 404), (None, 401)])
def test_administrative_denials_have_no_dml_or_enqueue(membership_env, actor, code):
    env = membership_env
    def snapshot():
        with env.factory() as db:
            return {t.name: db.execute(select(t).order_by(*t.primary_key.columns)).all() for t in Base.metadata.sorted_tables}
    before = snapshot()
    writes = []
    def record(_, __, sql, *args):
        if sql.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(sql)
    event.listen(env.engine, "before_cursor_execute", record)
    try:
        for method, suffix, body in ADMIN_ROUTES:
            result = env.client.request(method, "/v1/organizations/org" + suffix,
                headers=headers(actor) if actor else {}, **({"json": body} if body is not None else {}))
            assert result.status_code == code, (suffix, result.text)
    finally:
        event.remove(env.engine, "before_cursor_execute", record)
    assert before == snapshot() and not writes and not env.pool.jobs


def test_foreign_resource_ids_are_filtered_by_org(membership_env):
    env = membership_env
    invitation = issue(env)
    for method, path, body in [
        ("POST", f'/v1/organizations/other/invitations/{invitation["id"]}/revoke', {}),
        ("PATCH", "/v1/organizations/other/members/viewer", {"role": "member"}),
        ("DELETE", "/v1/organizations/other/members/viewer", None),
        ("POST", "/v1/organizations/other/ownership/transfer", {"user_id": "viewer"}),
    ]:
        response = env.client.request(method, path, headers=headers("outsider"), **({"json": body} if body else {}))
        assert response.status_code == 404, response.text
    assert len(env.pool.jobs) == 1


def test_last_owner_and_transfer_invariants(membership_env):
    env = membership_env
    with env.factory() as db:
        initial_version = db.get(Organization, "org").membership_version
    for method, body in [("PATCH", {"role": "viewer"}), ("DELETE", None)]:
        response = env.client.request(method, "/v1/organizations/org/members/owner", headers=headers("owner"), **({"json": body} if body else {}))
        assert response.status_code == 409 and response.json() == {"detail": "last_owner"}
    with env.factory() as db:
        assert db.get(Organization, "org").membership_version == initial_version
        assert db.query(AuditLog).count() == 0
    for target, code in [("missing", 404), ("owner", 409), ("unknown", 409), ("outsider", 404)]:
        response = env.client.post("/v1/organizations/org/ownership/transfer", headers=headers("owner"), json={"user_id": target})
        assert response.status_code == code
    assert env.client.patch("/v1/organizations/org/members/viewer", headers=headers("owner"), json={"role": "owner"}).status_code == 422
    result = env.client.post("/v1/organizations/org/ownership/transfer", headers=headers("owner"), json={"user_id": "viewer"})
    assert result.status_code == 204
    with env.factory() as db:
        assert db.get(Membership, ("owner", "org")).role == "member"
        assert db.get(Membership, ("viewer", "org")).role == "owner"
    assert env.client.delete("/v1/organizations/org/members/member", headers=headers("owner")).status_code == 403
    assert env.client.delete("/v1/organizations/org/members/viewer", headers=headers("viewer")).json() == {"detail": "last_owner"}


def test_self_demotion_and_removal_need_another_owner(membership_env):
    env = membership_env
    with env.factory() as db:
        db.add(Membership(user_id="second", organization_id="org", role="owner"))
        db.commit()
    result = env.client.patch("/v1/organizations/org/members/owner", headers=headers("owner"), json={"role": "viewer"})
    assert result.status_code == 200 and result.json()["role"] == "viewer" and result.json()["user_id"] == "owner"
    assert env.client.get("/v1/resolve", headers=headers("owner"), params={"org_slug": "org", "project_slug": "project"}).json()["membership"] == {"role": "viewer", "permissions": ["read"]}
    with env.factory() as db:
        db.get(Membership, ("owner", "org")).role = "owner"
        db.commit()
    assert env.client.delete("/v1/organizations/org/members/owner", headers=headers("owner")).status_code == 204
    assert env.client.get("/v1/resolve", headers=headers("owner"), params={"org_slug": "org", "project_slug": "project"}).status_code == 404


def test_transfer_failure_rolls_back_both_roles(membership_env):
    from app.domain.services.membership_service import transfer_ownership
    env = membership_env
    def fail_after_first_change(mapper, connection, target):
        raise RuntimeError("injected between writes")
    event.listen(Membership, "after_update", fail_after_first_change)
    try:
        with env.factory() as db, pytest.raises(RuntimeError, match="between writes"):
            transfer_ownership(db, "org", "owner", "viewer")
    finally:
        event.remove(Membership, "after_update", fail_after_first_change)
    with env.factory() as db:
        assert db.get(Membership, ("owner", "org")).role == "owner"
        assert db.get(Membership, ("viewer", "org")).role == "viewer"
        assert db.query(Membership).filter_by(organization_id="org", role="owner").count() == 1
        assert db.query(AuditLog).count() == 0


def test_removal_revokes_email_invites_and_preserves_key_and_sessions(membership_env):
    env = membership_env
    invitation = issue(env)
    raw_token = dispatch(env, invitation["id"])
    key, prefix = generate_api_key("prod")
    with env.factory() as db:
        db.add(Membership(user_id="recipient", organization_id="org", role="member"))
        db.add(Membership(user_id="recipient", organization_id="other", role="viewer"))
        db.add(ApiKey(id="key", project_id="project", prefix=prefix, hash=hash_api_key(key), name="key", environment="prod", scopes="read,ingest,evaluate"))
        db.commit()
    assert env.client.delete("/v1/organizations/org/members/recipient", headers=headers("owner")).status_code == 204
    assert env.client.post("/v1/invitations/accept", headers=headers("recipient"), json={"token": raw_token}).status_code == 400
    assert env.client.get("/v1/auth/session", headers=headers("recipient")).status_code == 200
    with env.factory() as db:
        assert db.get(User, "recipient").credential_version == 0
        assert db.get(Membership, ("recipient", "other")).role == "viewer"
        row = db.get(OrganizationInvitation, invitation["id"])
        assert row.status == "revoked" and row.token_hash is None
        for scope in ("read", "ingest", "evaluate"):
            assert authenticate_api_key(Request({"type": "http"}), key, db, scope).id == "project"
        assert db.get(ApiKey, "key").revoked_at is None


@pytest.mark.parametrize("scope", ["read", "ingest", "evaluate"])
def test_all_new_routes_require_personal_jwt_even_accept(membership_env, scope):
    env = membership_env
    key, prefix = generate_api_key("prod")
    with env.factory() as db:
        db.add(ApiKey(id="key", project_id="project", prefix=prefix, hash=hash_api_key(key), name="key", environment="prod", scopes=scope))
        db.commit()
    for method, suffix, body in ADMIN_ROUTES:
        result = env.client.request(method, "/v1/organizations/org" + suffix,
            headers={"X-EvalOps-Key": key}, **({"json": body} if body is not None else {}))
        assert result.status_code == 401
    for auth in [{}, {"X-EvalOps-Key": key}]:
        result = env.client.post("/v1/invitations/accept", headers=auth, json={"token": "a" * 43})
        assert result.status_code == 401
    assert not env.pool.jobs
    with env.factory() as db:
        assert db.get(ApiKey, "key").last_used_at is None
