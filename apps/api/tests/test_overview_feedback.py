"""Human feedback describes submissions on the overview's trace cohort."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.db import SessionLocal, engine
from app.main import app
from app.models import EvaluationRun, HumanFeedback, Membership, Organization, Project, Rubric, Trace, User
from app.security import create_access_token


NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
EMPTY = dict(feedback_count=0, trace_count=0, thumbs_up=0, thumbs_down=0, rating_count=0, avg_rating=None)


@pytest.fixture
def overview(monkeypatch):
    monkeypatch.setattr("app.domain.services.analytics_service.utcnow", lambda: NOW)
    monkeypatch.setattr("app.domain.services.quality_gate_service.utcnow", lambda: NOW)
    with SessionLocal() as db:
        db.add_all([User(id="member", email="member@example.com", name="Member"),
                    User(id="outsider", email="outsider@example.com", name="Outsider"),
                    Organization(id="org", name="Org", slug="org")])
        db.flush()
        db.add(Membership(user_id="member", organization_id="org", role="owner"))
        db.add_all([Project(id=id, organization_id="org", name=id, slug=id) for id in ("project", "other")])
        db.commit()
    headers = {"Authorization": "Bearer " + create_access_token(sub="member", email="member@example.com", name="Member")}
    return TestClient(app), headers


def trace(id, *, age=timedelta(), environment="prod", project="project", deleted=False):
    at = NOW - age
    with SessionLocal() as db:
        db.add(Trace(id=id, project_id=project, organization_id="org", name=id,
                     environment=environment, status="ok", started_at=at, ended_at=at,
                     duration_ms=10, created_at=at, deleted_at=NOW if deleted else None))
        db.commit()


def feedback(id, trace_id, **kwargs):
    with SessionLocal() as db:
        db.add(HumanFeedback(id=id, trace_id=trace_id, created_at=kwargs.pop("created_at", NOW), **kwargs))
        db.commit()


def get(overview, **params):
    client, headers = overview
    response = client.get("/v1/analytics/overview", headers=headers, params={"project_id": "project", **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_counts_submissions_distinct_traces_and_valid_signals_without_fanout(overview):
    trace("one")
    trace("two")
    feedback("both", "one", thumbs="up", rating=1, user_ref="same", comment="private")
    feedback("repeat", "one", thumbs="up", rating=2, user_ref="same")
    feedback("down", "two", thumbs="down", rating=2)
    feedback("comment", "two", comment="private")
    feedback("invalid", "one", thumbs="sideways", rating=9)
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        if "human_feedback" in statement.lower():
            statements.append(statement.lower())
    event.listen(engine, "before_cursor_execute", capture)
    try:
        body = get(overview, window="24h")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert body["human_feedback"] == dict(feedback_count=5, trace_count=2, thumbs_up=2, thumbs_down=1, rating_count=3, avg_rating=1.6667)
    assert len(statements) == 1
    assert "join" not in statements[0]
    assert "comment" not in statements[0] and "user_ref" not in statements[0]
    assert body["kpis"]["avg_score"] is None
    assert body["kpis"]["evaluated_traces"] == 0


@pytest.mark.parametrize("window,days", [("24h", 1), ("7d", 7), ("30d", 30), (None, 14)])
def test_cohort_uses_trace_cutoff_environment_project_and_soft_delete(overview, window, days):
    age = timedelta(days=days)
    trace("boundary", age=age)
    trace("old", age=age + timedelta(microseconds=1))
    trace("dev", environment="dev")
    trace("deleted", deleted=True)
    trace("other", project="other")
    for id in ("boundary", "old", "dev", "deleted", "other"):
        feedback("fb_" + id, id, thumbs="up", rating=5)
    params = {"window": window, "limit_days": 1} if window else {}
    body = get(overview, environment="prod", **params)
    assert body["kpis"]["traces"] == 1
    assert body["human_feedback"] == dict(feedback_count=1, trace_count=1, thumbs_up=1, thumbs_down=0, rating_count=1, avg_rating=5.0)
    assert get(overview, **params)["human_feedback"]["feedback_count"] == 2


def test_legacy_limit_days_and_late_feedback_follow_trace_cohort(overview):
    trace("included", age=timedelta(days=2))
    trace("old", age=timedelta(days=4))
    with SessionLocal() as db:
        db.add(Rubric(id="rubric", project_id="project", slug="quality"))
        db.flush()
        db.add(EvaluationRun(id="judge", project_id="project", trace_id="included", rubric_id="rubric",
                             rubric_version=1, triggered_by="test", status="completed", aggregate_score=0.37, passed=False))
        db.commit()
    client, headers = overview
    gate_url = "/v1/projects/project/quality-gate/status?window=7d"
    gate_before = client.get(gate_url, headers=headers)
    assert gate_before.status_code == 200
    before = get(overview, limit_days=3)
    feedback("late", "included", thumbs="down", created_at=NOW + timedelta(days=2))
    feedback("old_feedback", "included", rating=4, created_at=NOW - timedelta(days=60))
    feedback("new_on_old", "old", thumbs="up")
    after = get(overview, limit_days=3)
    assert before["human_feedback"] == EMPTY
    assert after["kpis"]["avg_score"] == 0.37
    assert after["kpis"]["evaluated_traces"] == 1
    assert after["human_feedback"] == dict(feedback_count=2, trace_count=1, thumbs_up=0, thumbs_down=1, rating_count=1, avg_rating=4.0)
    for key in ("kpis", "cost_by_day", "model_breakdown", "recent_flagged"):
        assert before[key] == after[key]
    assert client.get(gate_url, headers=headers).json() == gate_before.json()


@pytest.mark.parametrize("signals,expected", [
    ({}, EMPTY),
    ({"thumbs": "down"}, {**EMPTY, "feedback_count": 1, "trace_count": 1, "thumbs_down": 1}),
    ({"rating": 5}, {**EMPTY, "feedback_count": 1, "trace_count": 1, "rating_count": 1, "avg_rating": 5.0}),
    ({"rating": 0}, {**EMPTY, "feedback_count": 1, "trace_count": 1}),
])
def test_empty_and_single_signal_keep_stable_shape(overview, signals, expected):
    assert get(overview, window="24h")["human_feedback"] == EMPTY
    trace("one")
    if signals:
        feedback("one", "one", **signals)
    assert get(overview, window="24h")["human_feedback"] == expected


def test_overview_keeps_member_auth_without_adding_key_access(overview):
    client, headers = overview
    url = "/v1/analytics/overview?project_id=project"
    assert client.get(url).status_code == 401
    outsider = {"Authorization": "Bearer " + create_access_token(sub="outsider", email="outsider@example.com", name="Outsider")}
    assert client.get(url, headers=outsider).status_code == 404
    key = client.post("/v1/projects/project/api-keys", headers=headers, json={"name": "read", "environment": "prod", "scopes": ["read"]})
    assert key.status_code == 201, key.text
    assert client.get(url, headers={"X-EvalOps-Key": key.json()["key"]}).status_code == 401
