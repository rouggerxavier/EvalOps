"""Opt-in PostgreSQL races for runner leases on a dedicated disposable database.

Local: EVALOPS_LEASES_TEST_DATABASE_URL, only 127.0.0.1:15639/evalops_leases_test.
CI (migrate-postgres job): EVALOPS_OFFLINE_TEST_DATABASE_URL, only 127.0.0.1:15636/offline_test.
"""
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app import models as m
from app.db import Base, get_db
from app.main import app
import test_offline_task_api as harness
import test_runner_leases as t
from test_runner_lease_budgets import RUNTIME_BUDGET_CHANGES, assert_runtime_budget_revalidation
from test_runner_control import credential

TARGETS = {"EVALOPS_LEASES_TEST_DATABASE_URL": (15639, "evalops_leases_test"),
           "EVALOPS_OFFLINE_TEST_DATABASE_URL": (15636, "offline_test")}


def target():
    for name, (port, database) in TARGETS.items():
        if os.environ.get(name):
            parsed = make_url(os.environ[name])
            assert parsed.host == "127.0.0.1" and parsed.port == port and parsed.database == database
            return os.environ[name]
    pytest.skip("dedicated PostgreSQL target not configured")


@pytest.fixture()
def postgres(monkeypatch):
    url = target()
    admin = create_engine(url)
    schema = "leases_" + uuid4().hex
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
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


def parallel(*calls):
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return [future.result() for future in [pool.submit(call) for call in calls]]


def settlements(factory, execution_id):
    with factory() as db:
        return db.query(m.ExecutionLedgerEntry).filter_by(execution_id=execution_id, kind="settle").count()


@pytest.mark.parametrize("change", RUNTIME_BUDGET_CHANGES)
def test_postgres_runtime_budget_revalidation(postgres, change):
    assert_runtime_budget_revalidation(change)


def test_postgres_two_credentials_race_for_one_execution(postgres):
    ctx = t.setup()
    second = credential(ctx["headers"], {"id": ctx["runner"]})["key"]
    client = TestClient(app, raise_server_exceptions=False)
    responses = parallel(*[lambda key=key, idem=idem: client.post(f"/v1/runners/{ctx['runner']}/leases", headers={"X-EvalOps-Runner-Key": key, "Idempotency-Key": idem})
                           for key, idem in ((ctx["key"], "a"), (second, "b"))])
    assert [response.status_code for response in responses] == [200, 200]
    assert sorted(response.json()["lease"] is None for response in responses) == [False, True]
    idle_body = next(response.json() for response in responses if response.json()["lease"] is None)
    assert idle_body == {"lease": None, "retry_after_s": 5}
    with postgres() as db:
        assert db.query(m.ExecutionLease).count() == 1
        assert db.get(m.Execution, ctx["execution"]).status == "running"
        db.execute(text("SELECT id FROM projects WHERE id = :id FOR UPDATE"), {"id": ctx["project"]})
        db.execute(text("SELECT id FROM organizations WHERE id = :id FOR UPDATE"), {"id": ctx["org"]})
        idle_while_locked = client.post(f"/v1/runners/{ctx['runner']}/leases", headers={"X-EvalOps-Runner-Key": second, "Idempotency-Key": "idle-locked"})
        assert idle_while_locked.status_code == 200 and idle_while_locked.json() == {"lease": None, "retry_after_s": 5}
        db.rollback()


def test_postgres_duplicate_completions_settle_once(postgres):
    ctx = t.setup()
    lease = t.leased(ctx)
    responses = parallel(*[lambda: t.finish(ctx, lease, t.report())] * 3)
    assert [response.status_code for response in responses] == [200] * 3
    assert settlements(postgres, ctx["execution"]) == 1


def test_postgres_refused_completions_with_provided_cost_settle_once(postgres):
    headers, project, _ = harness.bootstrap()
    key, _, raw = harness.key_for(headers, project)
    t.configure(headers, project)
    sealed = t.plan(headers, project)
    ctx = {"headers": headers, "project": project, "runner": sealed["runner_id"],
           "key": credential(headers, {"id": sealed["runner_id"]})["key"], "execution": t.enqueue(key, project, sealed)["id"]}
    lease = t.leased(ctx)
    harness.client.post(f"/v1/projects/{project}/api-keys/{raw['id']}/revoke", headers=headers).raise_for_status()
    responses = parallel(*[lambda: t.finish(ctx, lease, t.report(amount="0.12345678"))] * 3)
    assert [response.status_code for response in responses] == [409] * 3
    assert settlements(postgres, ctx["execution"]) == 1
    with postgres() as db:
        reservation = db.get(m.ExecutionReservation, ctx["execution"])
        assert (reservation.state, reservation.spent_units, reservation.active) == ("settled", 12345678, False)


def test_postgres_cancel_and_complete_race_keep_one_terminal(postgres):
    ctx = t.setup()
    lease = t.leased(ctx)
    cancel, done = parallel(lambda: harness.client.post(f"/v1/executions/{ctx['execution']}/cancel", headers=ctx["headers"]),
                            lambda: t.finish(ctx, lease, t.report()))
    assert cancel.status_code == done.status_code == 200
    assert cancel.json()["status"] in {"running", "succeeded"} and done.json()["status"] == "succeeded"
    assert settlements(postgres, ctx["execution"]) == 1
    with postgres() as db:
        account = db.query(m.OrganizationExecutionAccount).one()
        assert (account.reserved_units, account.spent_units) == (0, 12345678)


def test_postgres_complete_and_expiry_race_never_settles_late(postgres):
    ctx = t.setup()
    lease = t.leased(ctx)
    t.expire(ctx["execution"])
    cancel, late = parallel(lambda: harness.client.post(f"/v1/executions/{ctx['execution']}/cancel", headers=ctx["headers"]),
                            lambda: t.finish(ctx, lease, t.report()))
    assert cancel.json()["status"] == "uncertain" and late.status_code == 409
    assert settlements(postgres, ctx["execution"]) == 0
    with postgres() as db:
        assert db.get(m.ExecutionReservation, ctx["execution"]).state == "unknown"
        assert db.query(m.ExecutionAttempt).filter_by(execution_id=ctx["execution"]).count() == 1


def test_postgres_disable_during_heartbeat_leaves_uncertain(postgres):
    ctx = t.setup()
    lease = t.leased(ctx)
    disable, beat = parallel(lambda: harness.client.post(f"/v1/runners/{ctx['runner']}/disable", headers={**ctx["headers"], "Idempotency-Key": "off"}),
                             lambda: t.beat(ctx, lease))
    assert disable.status_code == 200 and beat.status_code in {200, 401}
    assert t.beat(ctx, lease).status_code == 401
    with postgres() as db:
        assert db.get(m.Execution, ctx["execution"]).status == "uncertain"


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_runner_lease_migration_round_trip_refuses_evidence_loss(dialect, tmp_path):
    url, schema, admin, options = f"sqlite:///{tmp_path / 'leases.db'}", None, None, {}
    if dialect == "postgresql":
        url = target()
        admin = create_engine(url)
        schema = "leases_migration_" + uuid4().hex
        with admin.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        options = {"options": f"-csearch_path={schema}"}
    engine = create_engine(url, connect_args=options)
    env = {**os.environ, "DATABASE_URL": url, **({"PGOPTIONS": f"-csearch_path={schema}"} if schema else {})}
    def alembic(*args):
        return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True)
    try:
        assert alembic("upgrade", "head").returncode == 0
        assert alembic("downgrade", "0019_execution_ledger").returncode == 0
        assert alembic("upgrade", "head").returncode == 0
        if dialect == "postgresql":
            assert alembic("check").returncode == 0
        metadata = MetaData()
        metadata.reflect(engine)
        now = datetime.now(timezone.utc)
        label = {"label_schema_version": 1, "access_revision": 1, "origin_environments": ["dev"], "allowed_environments": ["dev"], "source_refs": []}
        rows = {
            "users": {"id": "u", "email": "u@example.com", "name": "U", "created_at": now},
            "organizations": {"id": "org", "name": "Org", "slug": "org", "created_at": now},
            "projects": {"id": "p", "organization_id": "org", "name": "Project", "slug": "p", "default_environment": "dev", "created_at": now},
            "executions": {"id": "x", "project_id": "p", "environment": "dev", "origin": "controlled_runner", "mode": "application_adapter", "status": "running",
                           "manifest_hash": "sha256:" + "0" * 64, "manifest_content": "{}", "access_label": label, "created_by": "u", "created_at": now},
            "runners": {"id": "r", "project_id": "p", "name": "R", "owner_user_id": "u", "capabilities": {}, "access_label": label, "created_at": now},
            "runner_credentials": {"id": "c", "runner_id": "r", "project_id": "p", "prefix": "evk", "hash": "h", "expires_at": now, "created_at": now},
            "execution_leases": {"execution_id": "x", "project_id": "p", "attempt_id": "a", "runner_id": "r", "credential_id": "c", "claim_key": "k",
                                 "token_hash": "sha256:" + "1" * 64, "state": "expired", "claimed_at": now, "expires_at": now},
            "execution_late_reports": {"id": "lr", "execution_id": "x", "project_id": "p", "attempt_id": "a", "reason": "lease_closed",
                                       "content": "{}", "content_hash": "sha256:" + "2" * 64, "created_at": now},
        }
        with engine.begin() as conn:
            for table, values in rows.items():
                conn.execute(metadata.tables[table].insert().values(**{key: value for key, value in values.items() if key in metadata.tables[table].c}))
        for statement in (
            "UPDATE execution_leases SET state='active'",
            r"""UPDATE execution_late_reports SET content='{"a"\:1}'""",
            "DELETE FROM execution_leases",
            "DELETE FROM execution_late_reports",
        ):
            with pytest.raises(Exception, match="immutable_task_resource"):
                with engine.begin() as conn:
                    conn.execute(text(statement))
        refused = alembic("downgrade", "0019_execution_ledger")
        assert refused.returncode != 0 and "runner_leases_downgrade_requires_empty_tables" in refused.stderr
        with engine.connect() as conn:
            assert conn.execute(text("SELECT state FROM execution_leases")).scalar_one() == "expired"
    finally:
        engine.dispose()
        if schema:
            with admin.begin() as conn:
                conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()
