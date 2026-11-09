"""Invitation proof, sanitization, state machine, and uncertain enqueue results."""
from datetime import datetime, timedelta, timezone
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.api import routes_memberships
from app.domain.services import membership_service as service
from app.domain.services.password_recovery import token_digest
from app.main import app
from app.models import AuditLog, Membership, OrganizationInvitation, User
from app.workers.invitation_worker import _dispatch
from membership_helpers import dispatch, headers, issue, membership_env


def accept(env, token, user="recipient"):
    return env.client.post("/v1/invitations/accept", headers=headers(user), json={"token": token})


def test_issue_send_accept_once_and_resolve_current_membership(membership_env, caplog):
    env = membership_env
    invitation = issue(env, " Recipient@Example.Invalid ", "member")
    assert invitation["email"] == "recipient@example.invalid" and invitation["status"] == "pending"
    assert set(invitation) == {"id", "organization_id", "email", "role", "invited_by_user_id", "status", "created_at", "expires_at", "accepted_at", "revoked_at"}
    assert datetime.fromisoformat(invitation["expires_at"]) - datetime.fromisoformat(invitation["created_at"]) == timedelta(hours=24)
    name, args, kwargs = env.pool.jobs[0]
    assert name == "send_invitation_job" and args == (invitation["id"],) and kwargs["_job_id"] == invitation["id"]
    assert 0 < kwargs["_expires"] <= 86400
    token = dispatch(env, invitation["id"])
    with env.factory() as db:
        stored = db.get(OrganizationInvitation, invitation["id"])
        assert stored.token_hash == token_digest(token)
        before_expiry = stored.expires_at
        dump = repr([db.execute(select(table)).all() for table in OrganizationInvitation.metadata.sorted_tables])
        assert token not in dump
    assert token not in json.dumps(invitation) + repr(env.pool.jobs) + caplog.text
    assert env.client.get("/v1/invitations/accept", params={"token": token}, headers=headers("recipient")).status_code == 405
    accepted = accept(env, token)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json() == {"organization_id": "org", "organization_slug": "org", "role": "member", "permissions": ["read", "write"], "already_member": False}
    assert accept(env, token).json() == {"detail": "invalid_invitation"}
    with env.factory() as db:
        row = db.get(OrganizationInvitation, invitation["id"])
        assert row.status == "accepted" and row.token_hash is None and row.expires_at == before_expiry
        assert db.get(User, "recipient").credential_version == 0
        assert all(token not in repr(a.payload) for a in db.query(AuditLog))
    resolved = env.client.get("/v1/resolve", headers=headers("recipient"), params={"org_slug": "org", "project_slug": "project"})
    assert resolved.json()["membership"] == {"role": "member", "permissions": ["read", "write"]}
    assert env.client.patch("/v1/organizations/org/members/recipient", headers=headers("owner"), json={"role": "viewer"}).status_code == 200
    assert env.client.get("/v1/resolve", headers=headers("recipient"), params={"org_slug": "org", "project_slug": "project"}).json()["membership"] == {"role": "viewer", "permissions": ["read"]}


@pytest.mark.parametrize("condition", ["email", "expiry", "revoked", "issuer_removed", "issuer_demoted", "tampered", "unknown"])
def test_invalid_proofs_are_uniform_and_do_not_consume(membership_env, condition):
    env = membership_env
    invitation = issue(env)
    token = dispatch(env, invitation["id"])
    with env.factory() as db:
        row = db.get(OrganizationInvitation, invitation["id"])
        if condition == "email":
            db.get(User, "recipient").email = "new@example.invalid"
        elif condition == "expiry":
            row.expires_at = datetime.now(timezone.utc)
        elif condition == "revoked":
            row.status, row.token_hash = "revoked", None
        elif condition == "issuer_removed":
            db.delete(db.get(Membership, ("owner", "org")))
        elif condition == "issuer_demoted":
            db.get(Membership, ("owner", "org")).role = "member"
        db.commit()
        original = (row.status, row.token_hash)
    if condition == "tampered":
        token = ("a" if token[0] != "a" else "b") + token[1:]
    if condition == "unknown":
        token = "a" * 43
    response = accept(env, token)
    assert response.status_code == 400 and response.json() == {"detail": "invalid_invitation"}
    with env.factory() as db:
        row = db.get(OrganizationInvitation, invitation["id"])
        assert (row.status, row.token_hash) == original
        assert db.get(Membership, ("recipient", "org")) is None


@pytest.mark.parametrize("role,permissions", [("owner", ["admin", "destructive", "read", "write"]), ("viewer", ["read"]), ("legacy", [])])
def test_already_member_consumes_without_role_promotion(membership_env, role, permissions):
    env = membership_env
    invitation = issue(env, role="member")
    token = dispatch(env, invitation["id"])
    with env.factory() as db:
        db.add(Membership(user_id="recipient", organization_id="org", role=role))
        db.commit()
    result = accept(env, token)
    assert result.status_code == 200 and result.json()["already_member"] is True
    assert result.json()["role"] == role and result.json()["permissions"] == permissions
    assert accept(env, token).status_code == 400
    assert env.client.post("/v1/organizations/org/invitations", headers=headers("owner"), json={"email": "recipient@example.invalid"}).json() == {"detail": "already_member"}


def test_reissue_revokes_old_link_and_terminal_status_survives_time(membership_env):
    env = membership_env
    first = issue(env)
    old = dispatch(env, first["id"])
    second = issue(env)
    assert second["id"] != first["id"] and accept(env, old).status_code == 400
    token = dispatch(env, second["id"])
    assert accept(env, token).status_code == 200
    with env.factory() as db:
        for row in db.query(OrganizationInvitation):
            row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
    listed = env.client.get("/v1/organizations/org/invitations", headers=headers("owner")).json()["data"]
    assert {r["status"] for r in listed} == {"revoked", "accepted"}
    assert env.client.post(f'/v1/organizations/org/invitations/{second["id"]}/revoke', headers=headers("owner")).json() == {"detail": "invitation_already_accepted"}
    assert env.client.post(f'/v1/organizations/org/invitations/{first["id"]}/revoke', headers=headers("owner")).status_code == 204


@pytest.mark.parametrize("root_path", ["", "/api"])
def test_secret_and_administrative_validation_is_sanitized(membership_env, root_path):
    env = membership_env
    client = TestClient(app, root_path=root_path)
    try:
        for payload in [{"token": "SECRET"}, {"token": ["SECRET"]}, {"token": "a" * 43, "extra": "SECRET"}, {}]:
            response = client.post("/v1/invitations/accept", headers=headers("recipient"), json=payload)
            assert response.status_code == 400 and response.json() == {"detail": "invalid_invitation"}
        for path, payload, method in [
            ("/invitations", {"email": "bad\r\nBcc:SECRET@example.invalid"}, "post"),
            ("/invitations", {"email": "first,second@example.invalid"}, "post"),
            ("/invitations", {"email": "recipient@example.invalid", "role": "owner"}, "post"),
            ("/members/viewer", {"role": "SECRET"}, "patch"),
            ("/ownership/transfer", {"user_id": ["SECRET"]}, "post"),
        ]:
            response = getattr(client, method)("/v1/organizations/org" + path, headers=headers("owner"), json=payload)
            assert response.status_code == 422 and response.json() == {"detail": "invalid_request"}
    finally:
        client.close()
    assert env.pool.jobs == []


def test_list_keyset_pagination_expiry_and_no_get_mutation(membership_env):
    env = membership_env
    ids = [issue(env, email=f"user{i}@example.invalid")["id"] for i in range(3)]
    with env.factory() as db:
        first = db.get(OrganizationInvitation, ids[0])
        first.expires_at = datetime.now(timezone.utc)
        db.commit()
    writes = []
    def before(_, __, statement, *args):
        if statement.lstrip().split()[0].upper() in {"UPDATE", "DELETE", "INSERT"}:
            writes.append(statement)
    event.listen(env.engine, "before_cursor_execute", before)
    try:
        all_rows, cursor = [], None
        while True:
            response = env.client.get("/v1/organizations/org/invitations", headers=headers("owner"), params={"limit": 1, **({"cursor": cursor} if cursor else {})})
            assert response.status_code == 200, response.text
            data = response.json()
            all_rows.extend(data["data"])
            cursor = data["next_cursor"]
            if not cursor:
                break
    finally:
        event.remove(env.engine, "before_cursor_execute", before)
    assert [row["id"] for row in all_rows] == ids and all_rows[0]["status"] == "expired" and not writes
    assert env.client.get("/v1/organizations/org/invitations", headers=headers("owner"), params={"cursor": "bad"}).status_code == 400
    assert env.client.get("/v1/organizations/org/invitations", headers=headers("owner"), params={"limit": 201}).status_code == 422


@pytest.mark.parametrize("outage", ["flag", "smtp", "redis", "queue", "enqueue"])
def test_unavailable_and_pending_compensation(membership_env, monkeypatch, outage):
    env = membership_env
    if outage == "flag":
        monkeypatch.setenv("EVALOPS_INVITATIONS_ENABLED", "false")
    if outage == "smtp":
        monkeypatch.delenv("EVALOPS_SMTP_HOST")
    if outage == "redis":
        monkeypatch.setattr(routes_memberships, "check_invitation_rate_limit", lambda *_: (_ for _ in ()).throw(RuntimeError("secret backend")))
    if outage == "queue":
        monkeypatch.setattr(app.state, "arq_pool", None)
    if outage == "enqueue":
        env.pool.effect = lambda *_: (_ for _ in ()).throw(RuntimeError("secret enqueue"))
    response = env.client.post("/v1/organizations/org/invitations", headers=headers("owner"), json={"email": "recipient@example.invalid"})
    assert response.status_code == 503 and response.json() == {"detail": "invitations_unavailable"}
    with env.factory() as db:
        rows = db.query(OrganizationInvitation).all()
        assert len(rows) == (1 if outage == "enqueue" else 0)
        if rows:
            assert rows[0].status == "failed" and rows[0].token_hash is None


@pytest.mark.parametrize("advanced", ["sending", "sent", "accepted", "revoked"])
def test_ambiguous_enqueue_preserves_confirmed_progress(membership_env, advanced):
    env = membership_env
    def effect(invitation_id):
        if advanced == "sending":
            with env.second_factory() as db:
                db.query(OrganizationInvitation).filter_by(id=invitation_id).update({"status": "sending", "token_hash": "b" * 64})
                db.commit()
        else:
            token = dispatch(env, invitation_id)
            if advanced == "accepted":
                with env.second_factory() as db:
                    service.accept_invitation(db, "recipient", token)
            elif advanced == "revoked":
                with env.second_factory() as db:
                    service.revoke_invitation(db, "org", "owner", invitation_id)
        raise RuntimeError("after redis write")
    env.pool.effect = effect
    result = issue(env)
    assert result["status"] == advanced
    assert len(env.pool.jobs) == 1
    with env.factory() as db:
        row = db.get(OrganizationInvitation, result["id"])
        assert row.status == advanced
        if advanced in {"accepted", "revoked"}:
            assert row.token_hash is None


def test_rate_limit_returns_retry_after(membership_env, monkeypatch):
    monkeypatch.setattr(routes_memberships, "check_invitation_rate_limit", lambda *_: 120)
    response = membership_env.client.post("/v1/organizations/org/invitations", headers=headers("owner"), json={"email": "recipient@example.invalid"})
    assert response.status_code == 429 and response.headers["Retry-After"] == "120"
    assert not membership_env.pool.jobs


def test_exact_expiry_and_all_terminal_states(membership_env, monkeypatch):
    env = membership_env
    invitation = issue(env)
    token = dispatch(env, invitation["id"])
    instant = datetime.now(timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant
    monkeypatch.setattr(service, "datetime", Clock)
    with env.factory() as db:
        row = db.get(OrganizationInvitation, invitation["id"])
        row.expires_at = instant
        db.commit()
        for status in ["pending", "sending", "sent", "failed", "accepted", "revoked"]:
            row.status = status
            assert service.effective_status(row, instant) == ("expired" if status in {"pending", "sending", "sent"} else status)
        db.rollback()
    assert accept(env, token).status_code == 400
    path = f'/v1/organizations/org/invitations/{invitation["id"]}/revoke'
    assert env.client.post(path, headers=headers("owner")).status_code == 204
    assert env.client.post(path, headers=headers("owner")).status_code == 204
    with env.factory() as db:
        assert db.get(OrganizationInvitation, invitation["id"]).token_hash is None


def test_unconfirmed_enqueue_and_busy_compensation_is_503(membership_env):
    env = membership_env
    holder = env.second_factory()
    lock = None
    def enqueue(invitation_id):
        nonlocal lock
        lock = service.organization_lock(holder, "org")
        lock.__enter__()
        raise RuntimeError("ambiguous dispatch")
    env.pool.effect = enqueue
    try:
        result = env.client.post("/v1/organizations/org/invitations", headers=headers("owner"), json={"email": "recipient@example.invalid"})
        assert result.status_code == 503 and result.json() == {"detail": "invitations_unavailable"}
    finally:
        if lock:
            lock.__exit__(None, None, None)
        holder.rollback()
        holder.close()
    with env.factory() as db:
        assert db.query(OrganizationInvitation).one().status == "pending"
    assert len(env.pool.jobs) == 1


def test_default_viewer_flag_does_not_block_existing_links_or_management(membership_env, monkeypatch):
    env = membership_env
    result = env.client.post("/v1/organizations/org/invitations", headers=headers("owner"), json={"email": "recipient@example.invalid"})
    assert result.status_code == 202 and result.json()["role"] == "viewer"
    token = dispatch(env, result.json()["id"])
    monkeypatch.setenv("EVALOPS_INVITATIONS_ENABLED", "false")
    monkeypatch.delenv("EVALOPS_SMTP_HOST")
    assert accept(env, token).status_code == 200
    assert env.client.get("/v1/organizations/org/invitations", headers=headers("owner")).status_code == 200
    assert env.client.patch("/v1/organizations/org/members/recipient", headers=headers("owner"), json={"role": "member"}).status_code == 200
    assert env.client.delete("/v1/organizations/org/members/recipient", headers=headers("owner")).status_code == 204
