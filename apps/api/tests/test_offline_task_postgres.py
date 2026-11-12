"""Opt-in real PostgreSQL gates; a dedicated disposable database is mandatory."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db import Base, get_db
from app.main import app
import test_offline_task_api as harness


@pytest.fixture()
def postgres(monkeypatch):
    target = os.environ.get("EVALOPS_OFFLINE_TEST_DATABASE_URL")
    if not target:
        pytest.skip("dedicated PostgreSQL target not configured")
    parsed = make_url(target)
    assert parsed.host == "127.0.0.1" and parsed.port == 15636 and parsed.database == "offline_test"
    admin = create_engine(target)
    schema = "task_" + uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(target, connect_args={"options": f"-csearch_path={schema}"})
    factory = sessionmaker(engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    def get_test_db():
        with factory() as db:
            yield db
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = get_test_db
    monkeypatch.setattr(harness, "SessionLocal", factory)
    try:
        yield factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_postgres_vertical_and_concurrent_receipts(postgres):
    headers, project, _ = harness.bootstrap()
    _, _, _, predictions = harness.fixture(headers, project)
    def create():
        return harness.post(f"/projects/{project}/task-evaluations", {"prediction_set_id": predictions["id"]}, headers, key="concurrent")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: create(), range(2)))
    assert first == second
    from app.models import TaskEvaluation
    with postgres() as db:
        assert db.query(TaskEvaluation).count() == 1


def test_postgres_transitive_access_restrictions(postgres):
    harness.test_neutral_owner_source_is_shared_only_explicitly_and_restriction_is_transitive()


def test_postgres_investigation_revision_compare_and_swap(postgres):
    headers, project, _ = harness.bootstrap()
    first = harness.post(f"/projects/{project}/investigations", {
        "environment": "dev", "state": {"title": "Concurrent investigation"}}, headers)
    path = f"/v1/investigations/{first['id']}"
    def patch(index):
        return harness.client.patch(path, headers={**headers, "If-Match": "1", "Idempotency-Key": f"revision-{index}"},
                                    json={"state": {"title": f"Writer {index}"}})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(patch, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    history = harness.client.get(path + "/revisions", headers=headers).json()["data"]
    assert [row["revision"] for row in history] == [1, 2]
    assert history[-1]["title"] == next(response.json()["title"] for response in responses if response.status_code == 200)


def test_postgres_external_capture_receipt_and_immutable_attempt(postgres):
    from test_execution_imports import payload
    from sqlalchemy.exc import DBAPIError
    headers, project, _ = harness.bootstrap()
    _, snapshot, model, predictions = harness.fixture(headers, project)
    body = payload(snapshot, model, predictions)
    def create():
        return harness.post(f"/projects/{project}/execution-imports", body, headers, key="concurrent-import")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: create(), range(2)))
    assert first == second
    from app.models import Execution, ExecutionAttempt
    with postgres() as db:
        assert db.query(Execution).count() == db.query(ExecutionAttempt).count() == 1
        with pytest.raises(DBAPIError, match="immutable_task_resource"):
            db.execute(text("UPDATE execution_attempts SET result_content='{}'")); db.commit()


def test_postgres_policy_revision_cas(postgres):
    headers, project, _ = harness.bootstrap()
    url = f"/v1/projects/{project}/execution-policy"
    def update(index):
        return harness.client.put(url, headers={**headers, "If-Match": "0", "Idempotency-Key": f"policy-{index}"}, json={"enabled": False})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(update, range(2)))
    assert sorted(row.status_code for row in responses) == [200, 409]
    from app.models import ExecutionPolicyRevision
    with postgres() as db:
        assert db.query(ExecutionPolicyRevision).count() == 1


def test_postgres_organization_budget_is_atomic_across_projects(postgres):
    from test_execution_budget import configure, plan, enqueue
    headers, project, org = harness.bootstrap()
    other = harness.post("/projects", {"organization_id": org, "name": "Other", "slug": "other"}, headers)["id"]
    configure(headers, project, cost="0.75", monthly="1.00", parallel=2)
    configure(headers, other, cost="0.75", monthly="1.00", parallel=2, organization=False)
    first = plan(headers, project, cost="0.75")
    second = plan(headers, other, cost="0.75")
    def admit(pair):
        identifier, sealed = pair
        return harness.client.post(f"/v1/projects/{identifier}/executions", headers={**headers, "Idempotency-Key": "admission"}, json={"plan_id": sealed["id"]})
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(admit, [(project, first), (other, second)]))
    assert sorted(row.status_code for row in responses) == [202, 402]
    from app.models import ExecutionReservation, ExecutionLedgerEntry, OrganizationExecutionAccount
    with postgres() as db:
        assert db.query(ExecutionReservation).count() == db.query(ExecutionLedgerEntry).count() == 1
        account = db.query(OrganizationExecutionAccount).one()
        assert (account.reserved_units, account.spent_units) == (75000000, 0)


@pytest.mark.parametrize("value", ["987654321.98765431", "999999999.99999999"])
def test_postgres_ledger_amounts_round_trip_exactly(postgres, value):
    from test_execution_budget import assert_exact_ledger
    headers, project, _ = harness.bootstrap()
    assert_exact_ledger(headers, project, value)


def test_postgres_cancel_and_admission_share_lock_order(postgres, monkeypatch):
    """Cancel in A and admission in B (same org/owner) must not deadlock on organization vs identity rows."""
    import threading
    from fastapi.testclient import TestClient
    from test_execution_budget import configure, plan, enqueue
    from app.domain.tasks import execution_plans
    headers, project, org = harness.bootstrap()
    other = harness.post("/projects", {"organization_id": org, "name": "Other", "slug": "other"}, headers)["id"]
    configure(headers, project, cost="0.25", monthly="1.00", parallel=4)
    configure(headers, other, cost="0.25", monthly="1.00", parallel=4, organization=False)
    queued = enqueue(headers, project, plan(headers, project, cost="0.25"))
    sealed = plan(headers, other, cost="0.25")
    barrier = threading.Barrier(2, timeout=3)
    original = execution_plans.authorization
    def meet():
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass  # the fixed order blocks the other side on the organization row, so it never arrives
    def paced(db, actor, request, project_id):
        # Widen the window: admission holds the organization, cancel holds user/membership.
        cancelling = request.url.path.endswith("/cancel")
        if not cancelling:
            meet()
        result = original(db, actor, request, project_id)
        if cancelling:
            meet()
        return result
    monkeypatch.setattr(execution_plans, "authorization", paced)
    client = TestClient(app, raise_server_exceptions=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cancel = pool.submit(client.post, f"/v1/executions/{queued['id']}/cancel", headers=headers)
        admit = pool.submit(client.post, f"/v1/projects/{other}/executions", headers={**headers, "Idempotency-Key": "race"}, json={"plan_id": sealed["id"]})
        statuses = (cancel.result().status_code, admit.result().status_code)
    assert statuses == (200, 202)
    from app.models import OrganizationExecutionAccount
    with postgres() as db:
        account = db.query(OrganizationExecutionAccount).one()
        assert (account.reserved_units, account.spent_units) == (25000000, 0)
