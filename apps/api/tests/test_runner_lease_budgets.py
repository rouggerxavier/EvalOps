"""Runtime budget revalidation through public APIs, without provider calls."""
import pytest

from app import models as m
import test_runner_leases as t


RUNTIME_BUDGET_CHANGES = ("overspend", "project_budget", "project_parallel", "organization_parallel")


def assert_runtime_budget_revalidation(change):
    """Shared HTTP/state assertions also run against the disposable PostgreSQL schema."""
    ctx = t.setup(monthly="3" if change == "overspend" else "10", parallel=2)
    first = t.leased(ctx)
    second = t.enqueue(ctx["headers"], ctx["project"], ctx["plan"])
    if change == "overspend":
        assert t.finish(ctx, first, t.report(amount="3.00000000")).status_code == 200
        response = t.claim(ctx, "after-overspend")
        assert response.status_code == 200 and response.json() == {"lease": None, "retry_after_s": 5}
        second_ctx = {**ctx, "execution": second["id"]}
        assert t.execution(second_ctx)["status"] == "cancelled"
        balance = t.budget(second_ctx)
        assert (balance["state"], balance["known_spent_usd"], balance["held_usd"], balance["slots_active"]) == (
            "settled", "0.00000000", "0.00000000", False)
        with t.h.SessionLocal() as db:
            assert db.get(m.ExecutionLease, second["id"]) is None
            account = db.query(m.OrganizationExecutionAccount).one()
            assert (account.reserved_units, account.spent_units) == (0, 300000000)
        return

    if change == "organization_parallel":
        assert t.claim(ctx, "second-claim").json()["lease"]["execution_id"] == second["id"]
        updated = t.h.client.put(f"/v1/projects/{ctx['project']}/organization-execution-budget",
            headers={**ctx["headers"], "If-Match": "1"},
            json={"enabled": True, "monthly_budget_usd": "10", "max_parallel": 1})
    else:
        if change == "project_parallel":
            assert t.claim(ctx, "second-claim").json()["lease"]["execution_id"] == second["id"]
        updated = t.h.client.put(f"/v1/projects/{ctx['project']}/execution-policy",
            headers={**ctx["headers"], "If-Match": "1", "Idempotency-Key": "tightened-policy"},
            json={"enabled": True, "allowed_adapters": [{"id": "fixture", "version": "1"}],
                  "max_cost_per_run_usd": "1", "monthly_budget_usd": "1.5" if change == "project_budget" else "10",
                  "max_parallel": 1 if change == "project_parallel" else 2})
    assert updated.status_code == 200, updated.text
    response = t.claim(ctx)
    assert response.status_code == 409 and response.json()["detail"] == "execution_lease_not_active"
    assert t.claim(ctx).status_code == 409
    assert t.beat(ctx, first).status_code == 409
    view = t.execution(ctx)
    assert view["status"] == "uncertain" and view["control"]["lease"]["state"] == "lost"
    assert len(view["attempts"]) == 1
    balance = t.budget(ctx)
    assert (balance["state"], balance["held_usd"], balance["slots_active"]) == ("unknown", "1.00000000", True)
    assert not any(entry["kind"] == "settle" for entry in balance["entries"])


@pytest.mark.parametrize("change", RUNTIME_BUDGET_CHANGES)
def test_runtime_budget_revalidation(change):
    assert_runtime_budget_revalidation(change)


def test_running_report_still_records_spend_after_other_execution_overspends():
    ctx = t.setup(monthly="3", parallel=2)
    first = t.leased(ctx)
    second = t.enqueue(ctx["headers"], ctx["project"], ctx["plan"])
    second_lease = t.claim(ctx, "second-claim").json()["lease"]
    assert second_lease["execution_id"] == second["id"]
    assert t.finish(ctx, first, t.report(amount="3.00000000")).status_code == 200
    assert t.finish(ctx, second_lease, t.report(amount="0.25000000")).status_code == 200
    with t.h.SessionLocal() as db:
        account = db.query(m.OrganizationExecutionAccount).one()
        assert (account.reserved_units, account.spent_units) == (0, 325000000)
        assert db.query(m.ExecutionLedgerEntry).filter_by(kind="settle").count() == 2


def test_expired_claim_replay_commits_expiry_before_refusal():
    ctx = t.setup()
    t.leased(ctx)
    t.expire(ctx["execution"])
    response = t.claim(ctx)
    assert response.status_code == 409
    view = t.execution(ctx)
    assert view["status"] == "uncertain" and view["control"]["lease"]["state"] == "expired"
    assert len(view["attempts"]) == 1
    assert t.budget(ctx)["slots_active"] is True
