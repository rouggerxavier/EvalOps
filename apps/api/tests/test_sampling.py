"""Sampling contract against SQLite by default and an explicit isolated Postgres target."""
from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, SessionLocal, get_db
from app.domain.services import sampling_service
from app.domain.services.sampling_service import process_sample
from app.main import app
from app.models import EvaluationRun, EvaluationSamplingJob, EvaluatorRow, Plan, UsageCounter, User, utcnow
from app.security import create_access_token
from app.workers.sampling_worker import dispatch_sampling_job, evaluate_sample_job

RUBRIC = """slug: sampling
name: Sampling
description: Deterministic checks

threshold: 0.5
aggregate: weighted_mean
evaluators:
  - id: length
    type: length_bounds
    config:
      target: trace.output.assistant_message
      min: 1
      max: 500
"""


@pytest.fixture
def env():
    target = os.getenv("SAMPLING_TEST_DATABASE_URL")
    engine = create_engine(target) if target else None
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False) if engine else SessionLocal
    if engine:
        Base.metadata.create_all(engine)
    def get_test_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = get_test_db
    client = TestClient(app)
    with factory() as db:
        db.add(User(id="sampling-user", email="sampling@example.com", name="Sampling"))
        db.commit()
    headers = {"Authorization": "Bearer " + create_access_token(sub="sampling-user", email="sampling@example.com", name="Sampling")}
    response = client.post("/v1/organizations", headers=headers, json={"name": "Sampling", "slug": "sampling"})
    assert response.status_code == 201, response.text
    org_id = response.json()["id"]
    project = client.post("/v1/projects", headers=headers,
                          json={"organization_id": org_id, "name": "Sampling", "slug": "sampling"}).json()
    project_id = project["id"]
    rubric = client.post(f"/v1/projects/{project_id}/rubrics", headers=headers, json={"yaml_source": RUBRIC})
    assert rubric.status_code == 201, rubric.text
    rubric_id = rubric.json()["rubric"]["id"]
    key = client.post(f"/v1/projects/{project_id}/api-keys", headers=headers,
                      json={"name": "Sampling", "environment": "prod", "scopes": ["read", "ingest", "evaluate"]}).json()["key"]
    yield {"client": client, "factory": factory, "headers": headers, "key": key, "project": project_id,
           "rubric": rubric_id, "org": org_id, "url": f"/v1/projects/{project_id}/evaluation-sampling"}
    app.dependency_overrides.pop(get_db, None)
    if engine:
        Base.metadata.drop_all(engine)
        engine.dispose()


def configure(env, percentage=100, **kwargs):
    return env["client"].put(env["url"], headers=env["headers"], json={
        "enabled": True, "percentage": percentage, "rubric_id": env["rubric"], "rubric_version": 1, **kwargs,
    })


def ingest(env, client_id="sample-1"):
    now = datetime.now(timezone.utc)
    response = env["client"].post("/v1/traces", headers={"X-EvalOps-Key": env["key"]}, json={"traces": [{
        "client_trace_id": client_id, "name": "sampling", "environment": "prod", "status": "ok",
        "started_at": now.isoformat(), "ended_at": (now + timedelta(seconds=1)).isoformat(),
        "spans": [{"client_span_id": "span", "type": "llm_call", "name": "response", "status": "ok",
                   "started_at": now.isoformat(), "ended_at": (now + timedelta(seconds=1)).isoformat(),
                   "messages_out": [{"role": "assistant", "content": "Hello"}]}],
    }]})
    assert response.status_code == 202, response.text
    assert response.json()["errors"] == [], response.text
    return response.json()["results"][0]["trace_id"]


class Queue:
    def __init__(self, fail=False):
        self.fail = fail
        self.jobs = []

    async def enqueue_job(self, name, **kwargs):
        if self.fail:
            raise ConnectionError("isolated queue unavailable")
        self.jobs.append((name, kwargs))
        return object()


def test_default_zero_and_hundred_only_select_new_traces(env):
    default = env["client"].get(env["url"], headers=env["headers"]).json()
    assert default == {"enabled": False, "percentage": 0, "rubric_id": None, "rubric_version": None, "updated_at": None}
    ingest(env, "before")
    assert configure(env, 0).status_code == 200
    ingest(env, "zero")
    assert configure(env).status_code == 200
    trace_id = ingest(env)
    assert ingest(env) == trace_id
    ingest(env, "before")
    with env["factory"]() as db:
        jobs = db.query(EvaluationSamplingJob).all()
        assert len(jobs) == 1 and jobs[0].trace_id == trace_id
        counter = db.query(UsageCounter).one()
        assert counter.traces_ingested == 3
    result = process_sample(env["factory"], trace_id)
    assert result["status"] == "completed", result
    assert process_sample(env["factory"], trace_id) == result
    with env["factory"]() as db:
        assert db.query(EvaluationRun).count() == 1
        run = db.query(EvaluationRun).one()
        assert run.triggered_by == "sampling" and run.status == "completed"
        assert db.get(EvaluationSamplingJob, trace_id).run_id == run.id
        assert db.query(UsageCounter).one().evaluations_run == 1


def test_queue_failure_does_not_undo_ingestion_and_is_recovered(env):
    configure(env)
    trace_id = ingest(env)
    ctx = {"db_session_factory": env["factory"], "redis": Queue(fail=True)}
    assert asyncio.run(dispatch_sampling_job(ctx)) == {"enqueued": 0, "failed": 1}
    response = env["client"].get(env["url"] + "/jobs", headers=env["headers"]).json()["data"]
    assert response[0]["status"] == "queue_error"
    assert response[0]["reason"] == "evaluation_queue_unavailable"
    assert ingest(env) == trace_id
    retry = env["client"].post(env["url"] + f"/jobs/{trace_id}/retry", headers=env["headers"])
    assert retry.status_code == 200
    ctx["redis"] = Queue()
    assert asyncio.run(dispatch_sampling_job(ctx)) == {"enqueued": 1, "failed": 0}
    name, kwargs = ctx["redis"].jobs[0]
    assert name == "evaluate_sample_job" and kwargs["trace_id"] == trace_id
    result = asyncio.run(evaluate_sample_job(ctx, trace_id))
    assert result["status"] == "completed"
    assert env["client"].post(env["url"] + f"/jobs/{trace_id}/retry", headers=env["headers"]).status_code == 409


def test_acknowledged_but_lost_queue_delivery_is_recovered(env):
    configure(env)
    trace_id = ingest(env)
    queue = Queue()
    ctx = {"db_session_factory": env["factory"], "redis": queue}
    assert asyncio.run(dispatch_sampling_job(ctx))["enqueued"] == 1
    assert asyncio.run(dispatch_sampling_job(ctx))["enqueued"] == 0
    with env["factory"]() as db:
        job = db.get(EvaluationSamplingJob, trace_id)
        job.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()
    assert asyncio.run(dispatch_sampling_job(ctx))["enqueued"] == 1
    assert queue.jobs[0][1]["_job_id"] != queue.jobs[1][1]["_job_id"]
    assert process_sample(env["factory"], trace_id)["status"] == "completed"
    assert process_sample(env["factory"], trace_id)["status"] == "completed"
    with env["factory"]() as db:
        assert db.query(EvaluationRun).count() == 1
        assert db.query(UsageCounter).one().evaluations_run == 1


def test_project_rubric_version_and_scope_isolation(env):
    client, headers = env["client"], env["headers"]
    other = client.post("/v1/projects", headers=headers, json={"organization_id": env["org"], "name": "Other", "slug": "other"}).json()["id"]
    other_rubric = client.post(f"/v1/projects/{other}/rubrics", headers=headers, json={"yaml_source": RUBRIC}).json()["rubric"]["id"]
    assert configure(env, rubric_id=other_rubric).status_code == 404
    assert configure(env, rubric_version=999).status_code == 422
    assert configure(env, rubric_id=None, rubric_version=None).status_code == 422
    assert configure(env, 101).status_code == 422
    assert configure(env, -1).status_code == 422
    assert client.get(f"/v1/projects/{other}/evaluation-sampling", headers={"X-EvalOps-Key": env["key"]}).status_code == 404
    read_key = client.post(f"/v1/projects/{env['project']}/api-keys", headers=headers,
                          json={"name": "Read only", "environment": "prod", "scopes": ["read"]}).json()["key"]
    assert client.put(env["url"], headers={"X-EvalOps-Key": read_key}, json={"enabled": False}).status_code == 403
    configure(env)
    trace_id = ingest(env)
    assert client.get(f"/v1/projects/{other}/evaluation-sampling/jobs", headers=headers).json() == {"data": []}
    assert client.post(f"/v1/projects/{other}/evaluation-sampling/jobs/{trace_id}/retry", headers=headers).status_code == 404


def test_snapshot_stays_on_pinned_version_and_disabled_stops_new_samples(env):
    configure(env)
    trace_id = ingest(env)
    client, headers = env["client"], env["headers"]
    result = client.post(f"/v1/rubrics/{env['rubric']}/versions", headers=headers, json={"yaml_source": RUBRIC})
    assert result.status_code == 201, result.text
    assert configure(env, enabled=False, rubric_version=2).status_code == 200
    ingest(env, "after-disable")
    assert process_sample(env["factory"], trace_id)["status"] == "completed"
    with env["factory"]() as db:
        assert db.query(EvaluationRun).one().rubric_version == 1
        assert db.query(EvaluationSamplingJob).count() == 1


def test_existing_manual_run_is_skipped_without_replacement(env):
    configure(env)
    trace_id = ingest(env)
    response = env["client"].post("/v1/evaluations/run", headers=env["headers"], json={
        "trace_id": trace_id, "rubric_id": env["rubric"], "rubric_version": 1, "triggered_by": "manual",
    })
    assert response.status_code == 201, response.text
    result = process_sample(env["factory"], trace_id)
    assert result["status"] == "skipped" and result["reason"] == "already_evaluated"
    with env["factory"]() as db:
        assert db.query(EvaluationRun).one().triggered_by == "manual"
        assert db.query(UsageCounter).one().evaluations_run == 1


def test_manual_run_of_another_version_does_not_complete_the_sample(env):
    configure(env)
    trace_id = ingest(env)
    client, headers = env["client"], env["headers"]
    assert client.post(f"/v1/rubrics/{env['rubric']}/versions", headers=headers,
                       json={"yaml_source": RUBRIC}).status_code == 201
    response = client.post("/v1/evaluations/run", headers=headers, json={
        "trace_id": trace_id, "rubric_id": env["rubric"], "rubric_version": 2, "triggered_by": "manual",
    })
    assert response.status_code == 201, response.text
    result = process_sample(env["factory"], trace_id)
    assert result["status"] == "completed"
    with env["factory"]() as db:
        run = db.get(EvaluationRun, result["run_id"])
        assert run.triggered_by == "sampling" and run.rubric_version == 1
        assert db.query(EvaluationRun).count() == 2
        assert db.query(UsageCounter).one().evaluations_run == 2


@pytest.mark.parametrize("blocked_by", ["quota", "budget"])
def test_quota_and_judge_budget_block_without_losing_trace(env, blocked_by, monkeypatch):
    from app.domain.evaluators.registry import REGISTRY
    def unexpected_judge(*args, **kwargs):
        pytest.fail("budget must block before calling a paid judge")
    monkeypatch.setitem(REGISTRY, "llm_judge", unexpected_judge)
    configure(env)
    trace_id = ingest(env)
    with env["factory"]() as db:
        plan = db.query(Plan).one()
        if blocked_by == "quota":
            plan.monthly_eval_limit = 0
        else:
            plan.monthly_judge_budget_usd = 0.01
            row = db.query(EvaluatorRow).one()
            row.type = "llm_judge"
            row.config = {"provider": "openai", "model": "gpt-4o-mini"}
            # Budget spend belongs to all projects in the org, irrespective of this trace.
            run = EvaluationRun(id="spent", project_id=env["project"], trace_id=trace_id,
                                rubric_id=env["rubric"], rubric_version=2, triggered_by="manual",
                                status="completed", cost_usd=1)
            db.add(run)
        db.commit()
    result = process_sample(env["factory"], trace_id)
    assert result["status"] == "blocked"
    assert result["reason"] == ("quota_exceeded" if blocked_by == "quota" else "judge_budget_exhausted")
    with env["factory"]() as db:
        assert db.get(EvaluationSamplingJob, trace_id).run_id is None
        assert db.query(UsageCounter).one().evaluations_run == 0
        assert db.query(UsageCounter).one().traces_ingested == 1


def test_evaluation_and_marker_rollback_together_on_failure(env, monkeypatch):
    configure(env)
    trace_id = ingest(env)
    original = sampling_service.evaluate_trace
    def fail_after_evaluation(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("failure before final commit")
    monkeypatch.setattr(sampling_service, "evaluate_trace", fail_after_evaluation)
    assert process_sample(env["factory"], trace_id)["status"] == "error"
    with env["factory"]() as db:
        assert db.query(EvaluationRun).count() == 0
        assert db.query(UsageCounter).one().evaluations_run == 0
        assert db.get(EvaluationSamplingJob, trace_id).run_id is None
    monkeypatch.setattr(sampling_service, "evaluate_trace", original)
    response = env["client"].post(env["url"] + f"/jobs/{trace_id}/retry", headers=env["headers"])
    assert response.status_code == 200
    assert process_sample(env["factory"], trace_id)["status"] == "completed"


def test_postgres_concurrent_delivery_spends_once(env, monkeypatch):
    with env["factory"]() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("requires explicit isolated Postgres target")
    configure(env)
    trace_id = ingest(env)
    entered, release = Event(), Event()
    original = sampling_service.evaluate_trace
    def hold_evaluation(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(sampling_service, "evaluate_trace", hold_evaluation)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(process_sample, env["factory"], trace_id)
        assert entered.wait(5)
        second = executor.submit(process_sample, env["factory"], trace_id)
        try:
            assert second.result(5) == {"status": "busy"}
        finally:
            release.set()
        assert first.result(10)["status"] == "completed"
    assert process_sample(env["factory"], trace_id)["status"] == "completed"
    with env["factory"]() as db:
        assert db.query(EvaluationRun).count() == 1
        assert db.query(UsageCounter).one().evaluations_run == 1
