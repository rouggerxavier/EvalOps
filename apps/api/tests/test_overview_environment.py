"""Attention and coverage must describe the selected environment and project."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import EvaluationRun, Membership, Organization, Project, Rubric, Trace, User
from app.security import create_access_token


@pytest.fixture
def overview():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add(User(id="usr_env", email="env@example.com", name="Environment"))
        db.add(Organization(id="org_env", name="Env", slug="env"))
        db.flush()
        db.add(Membership(user_id="usr_env", organization_id="org_env", role="owner"))
        db.add_all([Project(id=id, organization_id="org_env", name=id, slug=id) for id in ("project_env", "other_project")])
        db.flush()
        db.add(Rubric(id="rub_env", project_id="project_env", slug="quality"))
        db.flush()
        for id, environment, status, age, deleted, project in [
            ("dev_error", "dev", "error", 0, False, "project_env"),
            ("dev_partial", "dev", "partial", 0, False, "project_env"),
            ("dev_unevaluated", "dev", "ok", 0, False, "project_env"),
            ("prod_error", "prod", "error", 0, False, "project_env"),
            ("prod_ok", "prod", "ok", 0, False, "project_env"),
            ("staging_empty", "staging", "ok", 0, False, "project_env"),
            ("old_dev", "dev", "error", 10, False, "project_env"),
            ("deleted_dev", "dev", "error", 0, True, "project_env"),
            ("other_dev", "dev", "error", 0, False, "other_project"),
        ]:
            at = now - timedelta(days=age)
            db.add(Trace(id=id, project_id=project, organization_id="org_env", name=id,
                         environment=environment, status=status, started_at=at, ended_at=at,
                         duration_ms=1, created_at=at, deleted_at=now if deleted else None))
        db.flush()
        for id, trace, status, project, version, age in [
            ("dev_complete", "dev_error", "completed", "project_env", 1, 0),
            ("dev_repeat", "dev_error", "completed", "project_env", 2, 0),
            ("dev_failed", "dev_partial", "failed", "project_env", 1, 0),
            ("prod_complete", "prod_error", "completed", "project_env", 1, 0),
            ("old_trace_new_run", "old_dev", "completed", "project_env", 1, 0),
            ("old_run", "prod_ok", "completed", "project_env", 1, 10),
            ("deleted_run", "deleted_dev", "completed", "project_env", 1, 0),
            ("foreign_run", "dev_unevaluated", "completed", "other_project", 1, 0),
            ("foreign_trace", "other_dev", "completed", "project_env", 1, 0),
        ]:
            db.add(EvaluationRun(id=id, project_id=project, trace_id=trace, rubric_id="rub_env",
                                 rubric_version=version, triggered_by="test", status=status,
                                 created_at=now - timedelta(days=age)))
        db.commit()
    headers = {"Authorization": "Bearer " + create_access_token(sub="usr_env", email="env@example.com", name="Environment")}
    return TestClient(app), headers


def get(overview, endpoint, **params):
    client, headers = overview
    response = client.get(f"/v1/projects/project_env/{endpoint}", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("environment,ids", [
    ("dev", {"dev_error", "dev_partial"}), ("prod", {"prod_error"}), ("staging", set()),
    (None, {"dev_error", "dev_partial", "prod_error"}),
])
def test_attention_filters_before_counting_and_listing(overview, environment, ids):
    body = get(overview, "attention", **({"environment": environment} if environment else {}))
    assert body["count"] == len(ids)
    assert {item["trace_id"] for item in body["items"]} == ids
    if environment == "dev":
        assert {item["cause"] for item in body["items"]} == {"trace_error", "partial_trace"}


def test_attention_applies_environment_before_the_25_trace_limit(overview):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        for index in range(26):
            db.add(Trace(id=f"prod_noise_{index}", project_id="project_env", organization_id="org_env",
                         name="noise", environment="prod", status="error", started_at=now,
                         ended_at=now, duration_ms=1, created_at=now))
        db.commit()
    body = get(overview, "attention", environment="dev")
    assert body["count"] == 2
    assert {item["trace_id"] for item in body["items"]} == {"dev_error", "dev_partial"}
    assert get(overview, "attention")["count"] == 25


@pytest.mark.parametrize("environment,coverage,runs", [
    ("dev", 0.3333, 5), ("prod", 1, 1), ("staging", 0, 0), (None, 0.5, 6),
])
def test_coverage_scopes_denominator_completed_traces_and_run_count(overview, environment, coverage, runs):
    body = get(overview, "coverage", window="7d", **({"environment": environment} if environment else {}))
    assert body["data"] == [{"rubric_id": "rub_env", "rubric_slug": "quality", "coverage": coverage, "runs_7d": runs}]


def test_coverage_keeps_selected_window_separate_from_run_count(overview):
    row = get(overview, "coverage", environment="dev", window="30d")["data"][0]
    assert row["coverage"] == 0.5
    assert row["runs_7d"] == 5


@pytest.mark.parametrize("endpoint", ["attention", "coverage"])
def test_environment_validation_and_project_access_are_preserved(overview, endpoint):
    client, headers = overview
    assert client.get(f"/v1/projects/project_env/{endpoint}", headers=headers, params={"environment": "invalid"}).status_code == 422
    assert client.get(f"/v1/projects/project_env/{endpoint}").status_code == 401
    with SessionLocal() as db:
        db.add(User(id="usr_outsider", email="outside@example.com", name="Outside"))
        db.commit()
    outsider = {"Authorization": "Bearer " + create_access_token(sub="usr_outsider", email="outside@example.com", name="Outside")}
    assert client.get(f"/v1/projects/project_env/{endpoint}", headers=outsider, params={"environment": "dev"}).status_code == 404
