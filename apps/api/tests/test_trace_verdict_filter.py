"""Latest verdicts must survive history volume and filter before cursor pagination."""
from datetime import datetime, timedelta, timezone
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db import Base, SessionLocal, get_db
from app.main import app
from app.models import EvaluationRun, Rubric, Span, Trace, TraceFlag, User
from app.security import create_access_token

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


@pytest.fixture(params=["sqlite"] + (["postgres"] if os.getenv("R31_POSTGRES_URL") else []))
def ws(request):
    # The optional URL must point to a disposable, dedicated test database.
    pg = create_engine(os.environ["R31_POSTGRES_URL"]) if request.param == "postgres" else None
    factory = sessionmaker(pg, expire_on_commit=False) if pg else SessionLocal
    if pg:
        Base.metadata.create_all(pg)

    def database():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = database
    client = TestClient(app)
    with factory() as db:
        db.add(User(id="usr_verdict", email="verdict@example.com", name="Verdict"))
        db.commit()
        headers = {"Authorization": "Bearer " + create_access_token(sub="usr_verdict", email="verdict@example.com", name="Verdict")}
        org = client.post("/v1/organizations", headers=headers, json={"name": "Verdicts", "slug": "verdicts"}).json()
        project = client.post("/v1/projects", headers=headers, json={"organization_id": org["id"], "name": "Traces", "slug": "traces"}).json()
        db.add(Rubric(id="rb_verdict", project_id=project["id"], slug="verdict"))
        db.commit()
        yield {"db": db, "client": client, "headers": headers, "project": project["id"], "org": org["id"]}
    app.dependency_overrides.pop(get_db)
    if pg:
        Base.metadata.drop_all(pg)
        pg.dispose()


def trace(ws, id, **values):
    row = Trace(id=id, project_id=ws["project"], organization_id=ws["org"],
                name=id, environment="prod", status="ok", started_at=NOW,
                ended_at=NOW, duration_ms=3000, created_at=NOW)
    for key, value in values.items():
        setattr(row, key, value)
    ws["db"].add(row)
    ws["db"].flush()
    return id


def run(ws, trace_id, id, passed, score=None, version=1, **values):
    ws["db"].add(EvaluationRun(id=id, trace_id=trace_id, project_id=ws["project"],
                            rubric_id="rb_verdict", rubric_version=version, triggered_by="test",
                            status="completed", passed=passed, aggregate_score=score,
                            created_at=values.pop("created_at", NOW), **values))


def listing(ws, **params):
    ws["db"].commit()
    response = ws["client"].get("/v1/traces", headers=ws["headers"], params={"project_id": ws["project"], **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_verdicts_are_per_trace_even_beyond_100_global_runs(ws):
    expected = {}
    for verdict, passed, metadata in [
        ("approved", True, {"partial_failure": True}),
        ("rejected", False, {"partial_failure": True}),
        ("partial", None, {"partial_failure": True}),
        ("unknown", None, {}),
        ("unknown", None, {"partial_failure": False}),
        ("unknown", None, {"partial_failure": "true"}),
        ("unknown", None, {"partial_failure": "invalid"}),
        ("unknown", None, {"partial_failure": 1}),
        ("unknown", None, {"partial_failure": None}),
    ]:
        id = trace(ws, f"tr_{len(expected)}")
        run(ws, id, f"ev_{id}", passed, 1 if passed else None,
            run_metadata=metadata, created_at=NOW - timedelta(days=1))
        expected[id] = verdict
    expected[trace(ws, "tr_no_run")] = "unknown"
    noise = trace(ws, "tr_noise")
    for i in range(105):
        run(ws, noise, f"ev_noise_{i}", False, 0, version=i + 1)
    expected[noise] = "rejected"

    rows = listing(ws)["data"]
    assert {row["id"]: row["last_verdict"] for row in rows} == expected
    assert next(row for row in rows if row["id"] == "tr_0")["last_score"] == 1
    for verdict in ("approved", "rejected", "partial", "unknown"):
        assert {row["id"] for row in listing(ws, verdict=verdict)["data"]} == {
            id for id, value in expected.items() if value == verdict
        }


def test_verdict_filter_precedes_pagination(ws):
    approved = set()
    for i in range(55):
        id = trace(ws, f"tr_approved_{i:03}", created_at=NOW - timedelta(days=1))
        run(ws, id, f"ev_{i}", True, 1)
        approved.add(id)
        trace(ws, f"tr_newer_{i:03}")
    first = listing(ws, verdict="approved", limit=50)
    assert len(first["data"]) == 50
    assert first["next_cursor"]
    second = listing(ws, verdict="approved", limit=50, cursor=first["next_cursor"])
    assert len(second["data"]) == 5
    assert second["next_cursor"] is None
    assert {row["id"] for row in first["data"] + second["data"]} == approved
    selects = []

    def count_evaluation_queries(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "evaluation_runs" in statement:
            selects.append(statement)

    engine = ws["db"].get_bind()
    event.listen(engine, "before_cursor_execute", count_evaluation_queries)
    try:
        listing(ws, verdict="approved", limit=1)
        assert len(selects) == 1
        selects.clear()
        listing(ws, verdict="approved", limit=50)
        assert len(selects) == 1
    finally:
        event.remove(engine, "before_cursor_execute", count_evaluation_queries)
    unknown = listing(ws, verdict="unknown", limit=50)
    assert len(unknown["data"]) == 50
    assert len(listing(ws, verdict="unknown", cursor=unknown["next_cursor"])["data"]) == 5


def test_latest_run_breaks_timestamp_ties_by_id_for_score_and_verdict(ws):
    id = trace(ws, "tr_tie")
    run(ws, id, "ev_z_older", True, 1, created_at=NOW - timedelta(seconds=1))
    run(ws, id, "ev_a", True, 0.9, version=2)
    run(ws, id, "ev_b", False, 0.2, version=3)
    row = listing(ws)["data"][0]
    assert (row["last_score"], row["last_verdict"]) == (0.2, "rejected")
    assert listing(ws, verdict="approved")["data"] == []
    assert listing(ws, verdict="rejected")["data"][0]["id"] == id


def test_verdict_composes_with_existing_filters_and_read_key_project_scope(ws):
    target = trace(ws, "tr_target", status="partial", tags={"channel": "chat"},
                   user_ref="customer", metadata_json={"conversation_id": "conv"})
    run(ws, target, "ev_old", False, 0.1, created_at=NOW - timedelta(days=1))
    run(ws, target, "ev_new", True, 0.9, version=2)
    dev = trace(ws, "tr_dev", environment="dev")
    run(ws, dev, "ev_dev", True, 1)
    deleted = trace(ws, "tr_deleted", deleted_at=NOW)
    run(ws, deleted, "ev_deleted", True, 1)
    ws["db"].add(Span(id="sp_target", trace_id=target, type="llm_call", name="llm",
                      status="ok", started_at=NOW, ended_at=NOW, duration_ms=2500, model="model-a"))
    ws["db"].add(TraceFlag(id="flag_target", trace_id=target, org_id=ws["org"], user_id="usr_verdict", reason="manual"))
    params = dict(verdict="approved", environment="prod", status="error,partial", name="target",
                  since=(NOW - timedelta(hours=1)).isoformat(), until=(NOW + timedelta(hours=1)).isoformat(),
                  tag="channel:chat", user_ref="customer", model="model-a", conversation_id="conv",
                  q="target", failed=True, score_lt=0.5, flagged=True, duration_gt=2000, slow_kind="llm")
    assert [row["id"] for row in listing(ws, **params)["data"]] == [target]
    # failed/score_lt retain their legacy "any historical run" semantics.
    assert {row["id"] for row in listing(ws, verdict="approved")["data"]} == {target, dev}
    key = ws["client"].post(f"/v1/projects/{ws['project']}/api-keys", headers=ws["headers"],
                             json={"name": "reader", "environment": "prod", "scopes": ["read"]}).json()["key"]
    response = ws["client"].get("/v1/traces", headers={"X-EvalOps-Key": key}, params={"project_id": ws["project"], **params})
    assert response.status_code == 200, response.text
    assert [row["id"] for row in response.json()["data"]] == [target]
    other_org = ws["client"].post("/v1/organizations", headers=ws["headers"], json={"name": "Other", "slug": "other"}).json()
    other = ws["client"].post("/v1/projects", headers=ws["headers"], json={"organization_id": other_org["id"], "name": "Other", "slug": "other"}).json()
    assert ws["client"].get("/v1/traces", headers={"X-EvalOps-Key": key}, params={"project_id": other["id"], "verdict": "unknown"}).status_code == 404
    assert ws["client"].get("/v1/traces", headers=ws["headers"], params={"project_id": other["id"], "verdict": "approved"}).json()["data"] == []
    ws["db"].add(User(id="usr_outsider", email="outsider@example.com", name="Outsider"))
    ws["db"].commit()
    outsider = {"Authorization": "Bearer " + create_access_token(sub="usr_outsider", email="outsider@example.com", name="Outsider")}
    assert ws["client"].get("/v1/traces", headers=outsider, params={"project_id": ws["project"], "verdict": "approved"}).status_code == 404
    assert ws["client"].get("/v1/traces", headers=ws["headers"], params={"project_id": ws["project"], "verdict": "invalid"}).status_code == 422
