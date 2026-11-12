"""Independent engines/connections exercise organization serialization on PG16/SQLite."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Lock, local

from fastapi import HTTPException
import pytest
from sqlalchemy import event, text

from app.domain.services import membership_service as service
from app.models import Membership, OrganizationInvitation
from app.workers.invitation_worker import _dispatch
from membership_helpers import dispatch, issue, membership_env


def call(factory, function):
    try:
        with factory() as db:
            return (200, function(db))
    except HTTPException as exc:
        return (exc.status_code, exc.detail)


@contextmanager
def synchronized_org_reads(env):
    barrier, seen = Barrier(2), local()
    def synchronize(conn, cursor, statement, params, context, many):
        # SQLite contenders both observe the same version; PG contenders reach NOWAIT together.
        if statement.startswith("SELECT organizations.") and not getattr(seen, "arrived", False):
            seen.arrived = True
            barrier.wait(timeout=5)
    for engine in (env.engine, env.second_engine):
        event.listen(engine, "after_cursor_execute" if env.dialect == "sqlite" else "before_cursor_execute", synchronize)
    try:
        yield
    finally:
        for engine in (env.engine, env.second_engine):
            event.remove(engine, "after_cursor_execute" if env.dialect == "sqlite" else "before_cursor_execute", synchronize)


def race(env, first, second):
    with synchronized_org_reads(env), ThreadPoolExecutor(2) as executor:
        a = executor.submit(call, env.factory, first)
        b = executor.submit(call, env.second_factory, second)
        result = [a.result(timeout=10), b.result(timeout=10)]
    # A controlled conflict requires a new explicit request, never a hidden service retry.
    for index, operation in enumerate((first, second)):
        if result[index][0] == 409 and result[index][1] == "membership_conflict":
            result[index] = call(env.factory, operation)
    return result


def assert_owners(env):
    with env.factory() as db:
        assert db.query(Membership).filter_by(organization_id="org", role="owner").count() >= 1


def add_second_owner(env):
    with env.factory() as db:
        db.add(Membership(user_id="second", organization_id="org", role="owner"))
        db.commit()


def test_two_accepts_insert_at_most_once(membership_env):
    env = membership_env
    invitation = issue(env)
    token = dispatch(env, invitation["id"])
    outcomes = race(env, lambda db: service.accept_invitation(db, "recipient", token),
                    lambda db: service.accept_invitation(db, "recipient", token))
    assert sorted(r[0] for r in outcomes) == [200, 400]
    with env.factory() as db:
        assert db.query(Membership).filter_by(user_id="recipient", organization_id="org").count() == 1
        assert db.get(OrganizationInvitation, invitation["id"]).status == "accepted"


def test_accept_versus_revoke(membership_env):
    env = membership_env
    invitation = issue(env)
    token = dispatch(env, invitation["id"])
    outcomes = race(env, lambda db: service.accept_invitation(db, "recipient", token),
                    lambda db: service.revoke_invitation(db, "org", "owner", invitation["id"]))
    assert all(r[0] in {200, 400, 409} for r in outcomes)
    with env.factory() as db:
        row = db.get(OrganizationInvitation, invitation["id"])
        exists = db.get(Membership, ("recipient", "org")) is not None
        assert (row.status, exists) in {("accepted", True), ("revoked", False)}
        assert row.token_hash is None
    assert call(env.factory, lambda db: service.accept_invitation(db, "recipient", token))[0] == 400


def test_accept_versus_remove_existing_recipient(membership_env):
    env = membership_env
    invitation = issue(env)
    token = dispatch(env, invitation["id"])
    with env.factory() as db:
        db.add(Membership(user_id="recipient", organization_id="org", role="viewer"))
        db.commit()
    outcomes = race(env, lambda db: service.accept_invitation(db, "recipient", token),
                    lambda db: service.change_membership(db, "org", "owner", "recipient", None))
    assert outcomes[1][0] == 200 and outcomes[0][0] in {200, 400}
    with env.factory() as db:
        assert db.get(Membership, ("recipient", "org")) is None
        assert db.get(OrganizationInvitation, invitation["id"]).token_hash is None
    assert call(env.factory, lambda db: service.accept_invitation(db, "recipient", token))[0] == 400


@pytest.mark.parametrize("role", [None, "viewer"])
def test_accept_versus_remove_or_demote_issuer(membership_env, role):
    env = membership_env
    add_second_owner(env)
    invitation = issue(env)
    token = dispatch(env, invitation["id"])
    outcomes = race(env, lambda db: service.accept_invitation(db, "recipient", token),
                    lambda db: service.change_membership(db, "org", "second", "owner", role))
    assert outcomes[1][0] == 200 and outcomes[0][0] in {200, 400}
    assert call(env.factory, lambda db: service.accept_invitation(db, "recipient", token))[0] == 400
    with env.factory() as db:
        assert (db.get(Membership, ("recipient", "org")) is not None) == (outcomes[0][0] == 200)
    assert_owners(env)


@pytest.mark.parametrize("role", [None, "viewer"])
def test_two_owners_cannot_remove_or_demote_each_other(membership_env, role):
    env = membership_env
    add_second_owner(env)
    outcomes = race(env, lambda db: service.change_membership(db, "org", "owner", "second", role),
                    lambda db: service.change_membership(db, "org", "second", "owner", role))
    assert sorted(r[0] for r in outcomes) in ([200, 403], [200, 404])
    assert_owners(env)


@pytest.mark.parametrize("second_operation", ["remove", "transfer"])
def test_transfer_versus_remove_or_transfer(membership_env, second_operation):
    env = membership_env
    add_second_owner(env)
    other = (lambda db: service.change_membership(db, "org", "second", "viewer", None)) if second_operation == "remove" else (
        lambda db: service.transfer_ownership(db, "org", "second", "viewer"))
    outcomes = race(env, lambda db: service.transfer_ownership(db, "org", "owner", "viewer"), other)
    assert all(r[0] in {200, 404, 409} for r in outcomes)
    assert any(r[0] == 200 for r in outcomes)
    if second_operation == "remove":
        with env.factory() as db:
            assert db.get(Membership, ("viewer", "org")) is None
    assert_owners(env)


def test_two_issues_leave_only_one_usable_invitation(membership_env):
    env = membership_env
    operation = lambda db: service.create_invitation(db, "org", "owner", "recipient@example.invalid", "viewer")
    outcomes = race(env, operation, operation)
    assert [r[0] for r in outcomes] == [200, 200]
    with env.factory() as db:
        rows = db.query(OrganizationInvitation).all()
        assert len(rows) == 2 and sorted(r.status for r in rows) == ["pending", "revoked"]
        assert len({r.id for r in rows}) == 2


def test_two_workers_send_once(membership_env):
    env = membership_env
    invitation = issue(env)
    sent, guard = [], Lock()
    def mailer(cfg, recipient, token):
        with guard:
            sent.append(token)
    with synchronized_org_reads(env), ThreadPoolExecutor(2) as executor:
        futures = [executor.submit(_dispatch, factory, invitation["id"], mailer)
                   for factory in (env.factory, env.second_factory)]
        for future in futures:
            future.result(timeout=10)
    # Retrying after either lock conflict or completed claim cannot deliver twice.
    _dispatch(env.factory, invitation["id"], mailer)
    assert len(sent) == 1
    with env.factory() as db:
        assert db.get(OrganizationInvitation, invitation["id"]).status == "sent"


def test_busy_lock_is_controlled_and_unknown_db_errors_propagate(membership_env):
    env = membership_env
    with env.factory() as first:
        with service.organization_lock(first, "org"):
            result = call(env.second_factory, lambda db: service.change_membership(db, "org", "owner", "viewer", "member"))
            assert result == (409, "membership_conflict")
            first.rollback()
    assert call(env.factory, lambda db: service.change_membership(db, "org", "owner", "viewer", "member"))[0] == 200
    with env.factory() as db, pytest.raises(Exception) as error:
        with service.organization_lock(db, "org"):
            db.execute(text("SELECT * FROM missing_r2_table"))
    assert not isinstance(error.value, HTTPException)
