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
