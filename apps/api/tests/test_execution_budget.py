"""No provider calls: exact quota accounting and plan/credential sealing through HTTP."""
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import models as m
from app.db import Base, SessionLocal, engine
from app.domain.tasks import execution_budget as b
import test_offline_task_api as h
from test_execution_imports import payload as import_payload
from test_runner_control import create_runner


@pytest.fixture(autouse=True)
def isolated():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


def configure(headers, project, *, cost="1", monthly="1", parallel=2, organization=True):
    response = h.client.put(f"/v1/projects/{project}/execution-policy", headers={**headers, "If-Match": "0", "Idempotency-Key": "policy"}, json={
        "enabled": True, "allowed_adapters": [{"id": "fixture", "version": "1"}], "max_cost_per_run_usd": cost,
        "monthly_budget_usd": monthly, "max_parallel": parallel})
    assert response.status_code == 200, response.text
    if organization:
        response = h.client.put(f"/v1/projects/{project}/organization-execution-budget", headers={**headers, "If-Match": "0"},
                               json={"enabled": True, "monthly_budget_usd": monthly, "max_parallel": parallel})
        assert response.status_code == 200, response.text


def plan(headers, project, *, cost="1"):
    _, snapshot, model, predictions = h.fixture(headers, project)
    runner = create_runner(headers, project)
    manifest = import_payload(snapshot, model, predictions)["manifest"]
    manifest["limits"]["max_cost_usd"] = cost
    return h.post(f"/projects/{project}/execution-plans", {"runner_id": runner["id"], "manifest": manifest}, headers)


def enqueue(headers, project, sealed, **kwargs):
    return h.post(f"/projects/{project}/executions", {"plan_id": sealed["id"]}, headers, expected=kwargs.pop("expected", 202), **kwargs)


def test_exact_fractional_reservations_and_known_zero_cancellation():
    headers, project, org = h.bootstrap()
    configure(headers, project, cost="0.00000001", monthly="0.00000003", parallel=100)
    sealed = plan(headers, project, cost="0.00000001")
    first = enqueue(headers, project, sealed, key="first")
    assert enqueue(headers, project, sealed, key="first") == first
    enqueue(headers, project, sealed); enqueue(headers, project, sealed)
    enqueue(headers, project, sealed, expected=402)
    with SessionLocal() as db:
        reservation = db.get(m.ExecutionReservation, first["id"])
        assert reservation.reserved_units == 1
        account = db.get(m.OrganizationExecutionAccount, (org, reservation.period))
        assert (account.reserved_units, account.spent_units) == (3, 0)
        assert db.query(m.Execution).filter_by(origin="controlled_runner").count() == 3
        db.get(m.Execution, first["id"]).status = "cancelled"
        b.settle(db, reservation, amount=Decimal("0"), actor_id="user", measurement_source="cancelled_before_lease", pricing_version="fixture@1")
        reservation.active = False
        db.commit()
        assert db.get(m.OrganizationExecutionAccount, (org, reservation.period)).reserved_units == 2
        assert sum(row.amount_units for row in db.query(m.ExecutionLedgerEntry).filter_by(kind="reserve")) == 3
        for statement in ("UPDATE execution_ledger_entries SET amount_units=0", "DELETE FROM execution_ledger_entries"):
            with pytest.raises(DBAPIError, match="immutable_task_resource"):
                db.execute(text(statement)); db.commit()
            db.rollback()
    enqueue(headers, project, sealed)


def test_execution_requires_write_and_evaluate_and_keeps_original_identity():
    headers, project, _ = h.bootstrap()
    configure(headers, project)
    sealed = plan(headers, project)
    key, principal, raw = h.key_for(headers, project, scopes=("read", "evaluate"))
    enqueue(key, project, sealed, expected=403)
    key, principal, raw = h.key_for(headers, project)
    execution = enqueue(key, project, sealed)
    assert execution["status"] == "queued" and execution["capture_origin"] == "controlled_runner"
    with SessionLocal() as db:
        context = db.get(m.ExecutionSchedule, execution["id"]).actor_context
        assert context["key_id"] == raw["id"] and context["principal_id"] == principal["id"]
        assert key["X-EvalOps-Key"] not in str(context)
        assert db.query(m.ExecutionLedgerEntry).count() == 1


def test_changed_policy_and_cross_project_plan_are_rejected_without_reservation():
    headers, project, org = h.bootstrap()
    configure(headers, project)
    sealed = plan(headers, project)
    other = h.post("/projects", {"organization_id": org, "slug": "other", "name": "Other"}, headers)
    enqueue(headers, other["id"], sealed, expected=404)
    response = h.client.put(f"/v1/projects/{project}/execution-policy", headers={**headers, "If-Match": "1", "Idempotency-Key": "new-policy"}, json={"enabled": False})
    assert response.status_code == 200
    enqueue(headers, project, sealed, expected=403)
    with SessionLocal() as db:
        assert db.query(m.ExecutionReservation).count() == db.query(m.ExecutionLedgerEntry).count() == 0


def test_unknown_holds_budget_and_slots_across_periods(monkeypatch):
    monkeypatch.setattr(b, "current_period", lambda: "2026-01")
    headers, project, org = h.bootstrap()
    configure(headers, project, cost="0.01", monthly="1", parallel=1)
    sealed = plan(headers, project, cost="0.01")
    execution = enqueue(headers, project, sealed)
    with SessionLocal() as db:
        reservation = db.get(m.ExecutionReservation, execution["id"])
        reservation.state = "unknown"
        db.get(m.Execution, execution["id"]).status = "uncertain"
        db.commit()
    monkeypatch.setattr(b, "current_period", lambda: "2026-02")
    enqueue(headers, project, sealed, expected=429)
    with SessionLocal() as db:
        reservation = db.get(m.ExecutionReservation, execution["id"])
        assert reservation.spent_units is None and reservation.active is True


@pytest.mark.parametrize("value", [True, "NaN", "Infinity", "0.000000001", "-1", "1000000001"])
def test_money_rejects_nonfinite_subunit_and_out_of_range(value):
    with pytest.raises(ValueError):
        b.units(value)


def test_cancel_queued_releases_hold_once_without_running_code():
    headers, project, _ = h.bootstrap()
    configure(headers, project)
    sealed = plan(headers, project)
    execution = enqueue(headers, project, sealed)
    path = f"/v1/executions/{execution['id']}"
    first = h.client.post(path + "/cancel", headers=headers)
    assert first.status_code == 200 and first.json()["status"] == "cancelled"
    assert h.client.post(path + "/cancel", headers=headers).json() == first.json()
    balance = h.client.get(path + "/budget", headers=headers).json()
    assert balance["held_usd"] == balance["known_spent_usd"] == "0.00000000"
    assert balance["slots_active"] is False
    assert [entry["kind"] for entry in balance["entries"]].count("release") == 1
    enqueue(headers, project, sealed)


def test_original_credential_revalidated_after_admission_without_releasing_unknown_hold():
    from fastapi import HTTPException
    from app.domain.tasks.execution_plans import original_actor
    headers, project, _ = h.bootstrap()
    configure(headers, project)
    sealed = plan(headers, project)
    key, _, raw = h.key_for(headers, project)
    execution = enqueue(key, project, sealed)
    h.client.post(f"/v1/projects/{project}/api-keys/{raw['id']}/revoke", headers=headers).raise_for_status()
    with SessionLocal() as db:
        row = db.get(m.Execution, execution["id"])
        schedule = db.get(m.ExecutionSchedule, row.id)
        with pytest.raises(HTTPException) as error:
            original_actor(db, row, schedule)
        assert error.value.status_code == 401
        assert db.get(m.ExecutionReservation, row.id).reserved_units == 100000000
        assert db.get(m.ExecutionReservation, row.id).spent_units is None


def test_overspend_remains_evidence_and_blocks_next_admission():
    headers, project, org = h.bootstrap()
    configure(headers, project, cost="0.02", monthly="0.03", parallel=2)
    sealed = plan(headers, project, cost="0.02")
    execution = enqueue(headers, project, sealed)
    with SessionLocal() as db:
        reservation = db.get(m.ExecutionReservation, execution["id"])
        db.get(m.Execution, execution["id"]).status = "succeeded"
        b.settle(db, reservation, amount=Decimal("0.04"), actor_id="user", measurement_source="fixture_report", pricing_version="fixture@1")
        reservation.active = False
        db.commit()
        account = db.get(m.OrganizationExecutionAccount, (org, reservation.period))
        assert account.spent_units == 4000000 and account.reserved_units == 0
    enqueue(headers, project, sealed, expected=402)


def assert_exact_ledger(headers, project, value):
    configure(headers, project, cost=value, monthly="1000000000", parallel=1)
    execution = enqueue(headers, project, plan(headers, project, cost=value))
    path = f"/v1/executions/{execution['id']}"
    assert h.client.post(path + "/cancel", headers=headers).status_code == 200
    balance = h.client.get(path + "/budget", headers=headers).json()
    assert balance["reserved_limit_usd"] == value
    assert {entry["kind"]: entry["amount_usd"] for entry in balance["entries"]} == {"reserve": value, "settle": "0.00000000", "release": value}


@pytest.mark.parametrize("value", ["987654321.98765431", "999999999.99999999"])
def test_ledger_amounts_round_trip_exactly(value):
    headers, project, _ = h.bootstrap()
    assert_exact_ledger(headers, project, value)
