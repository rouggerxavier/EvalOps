"""Organization quota alerts: transactional copies in each active project's bell."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db import Base, SessionLocal
from app.domain.services import usage_service as usage
from app.models import Notification, Organization, Project, UsageCounter


@pytest.fixture(params=["sqlite", "postgres"])
def sessions(request):
    if request.param == "sqlite":
        yield SessionLocal
        return
    url = os.getenv("QUOTA_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set QUOTA_TEST_DATABASE_URL to the isolated evalops_quota PostgreSQL database")
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql" and parsed.database == "evalops_quota"
    engine = create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def seed(sessions):
    with sessions() as db:
        db.add_all([
            Organization(id="org_quota", name="Quota", slug="quota"),
            Organization(id="org_other", name="Other", slug="other"),
        ])
        db.flush()
        db.add_all([
            Project(id="prj_quota", organization_id="org_quota", name="One", slug="one"),
            Project(id="prj_sibling", organization_id="org_quota", name="Two", slug="two"),
            Project(id="prj_archived", organization_id="org_quota", name="Old", slug="old", archived_at=datetime.now(timezone.utc)),
            Project(id="prj_other", organization_id="org_other", name="Other", slug="other"),
        ])
        usage.set_org_plan_limits(db, "org_quota", monthly_trace_limit=100, monthly_eval_limit=100,
                                  monthly_export_limit=100, monthly_span_limit=100, monthly_token_limit=100)
        usage.set_org_plan_limits(db, "org_other", monthly_trace_limit=100)
        usage.get_or_create_counter(db, "org_quota", usage.current_period())
        db.commit()


@pytest.mark.parametrize("delta,field", [
    ("traces", "traces_ingested"), ("evals", "evaluations_run"),
    ("exports", "exports_created"), ("spans", "spans_ingested"), ("tokens", "tokens_ingested"),
])
def test_threshold_fanout_dedup_and_402(sessions, delta, field):
    seed(sessions)
    with sessions() as db:
        project = db.get(Project, "prj_quota")
        usage.apply_usage_with_quota(db, project, **{delta: 79})
        db.commit()
        assert db.query(Notification).count() == 0
        usage.apply_usage_with_quota(db, project, **{delta: 1})
        db.commit()
        rows = db.query(Notification).all()
        assert {row.project_id for row in rows} == {"prj_quota", "prj_sibling"}
        assert all(row.kind == "warn" and "organização" in row.title for row in rows)
        assert all(row.meta == {"scope": "organization", "organization_id": "org_quota",
                               "period": usage.current_period(), "resource": field,
                               "threshold_percent": 80, "used": 80, "limit": 100} for row in rows)
        rows[0].read_at = datetime.now(timezone.utc)
        db.commit()
        usage.apply_usage_with_quota(db, db.get(Project, "prj_sibling"), **{delta: 20})
        db.commit()
        assert db.query(Notification).count() == 2
        assert sum(row.read_at is not None for row in db.query(Notification)) == 1
        with pytest.raises(HTTPException) as exc:
            usage.apply_usage_with_quota(db, project, **{delta: 1})
        assert exc.value.status_code == 402
        assert exc.value.detail == {"error": "quota_exceeded", "field": field, "limit": 100}
        db.rollback()
        assert getattr(db.query(UsageCounter).filter_by(organization_id="org_quota").one(), field) == 100
        assert db.query(Notification).count() == 2


def test_jump_rollback_rollover_and_org_isolation(sessions, monkeypatch):
    seed(sessions)
    with sessions() as db:
        project = db.get(Project, "prj_quota")
        usage.apply_usage_with_quota(db, project, traces=79)
        usage.apply_usage_with_quota(db, project, traces=21)
        db.flush()
        db.rollback()
        assert db.query(Notification).count() == 0
        assert db.query(UsageCounter).filter_by(organization_id="org_quota").one().traces_ingested == 0
        usage.apply_usage_with_quota(db, project, traces=100)
        db.commit()
        assert db.query(Notification).count() == 2
        usage.apply_usage_with_quota(db, db.get(Project, "prj_other"), traces=80)
        db.commit()
        assert db.query(Notification).filter_by(project_id="prj_other").count() == 1
        monkeypatch.setattr(usage, "current_period", lambda: "2099-02")
        usage.apply_usage_with_quota(db, project, traces=80)
        db.commit()
        assert db.query(Notification).count() == 5
        assert sum(row.meta["period"] == "2099-02" for row in db.query(Notification)) == 2


def test_multiple_increments_same_transaction_and_no_fake_judge_alert(sessions):
    seed(sessions)
    with sessions() as db:
        usage.increment_usage(db, "org_quota", traces=79, cost_usd=1_000)
        usage.increment_usage(db, "org_quota", traces=1)
        usage.increment_usage(db, "org_quota", traces=1)
        db.commit()
        assert db.query(UsageCounter).filter_by(organization_id="org_quota").one().traces_ingested == 81
        assert db.query(Notification).count() == 2
        assert all(row.meta["resource"] == "traces_ingested" for row in db.query(Notification))


def test_plan_change_does_not_repeat_alert_and_new_projects_wait_for_crossing(sessions):
    seed(sessions)
    with sessions() as db:
        project = db.get(Project, "prj_quota")
        usage.apply_usage_with_quota(db, project, traces=80)
        db.commit()
        db.add(Project(id="prj_later", organization_id="org_quota", name="Later", slug="later"))
        db.commit()
        usage.apply_usage_with_quota(db, project, traces=1)
        db.commit()
        assert db.query(Notification).filter_by(project_id="prj_later").count() == 0
        usage.set_org_plan_limits(db, "org_quota", monthly_trace_limit=200)
        db.commit()
        usage.apply_usage_with_quota(db, project, traces=79)
        db.commit()
        assert db.query(Notification).count() == 3
        assert db.query(Notification).filter_by(project_id="prj_quota").count() == 1
        assert db.query(Notification).filter_by(project_id="prj_sibling").count() == 1


def test_over_limit_batch_cannot_leave_partial_usage_or_alerts(sessions):
    seed(sessions)
    with sessions() as db:
        project = db.get(Project, "prj_quota")
        with pytest.raises(HTTPException) as exc:
            usage.apply_usage_with_quota(db, project, traces=80, evals=101)
        assert exc.value.status_code == 402
        db.commit()
        assert db.query(Notification).count() == 0
        row = db.query(UsageCounter).filter_by(organization_id="org_quota").one()
        assert row.traces_ingested == 0 and row.evaluations_run == 0


@pytest.mark.parametrize("delta,total,accepted", [(5, 90, 4), (10, 100, 3)])
def test_concurrent_preflight_does_not_lose_usage_or_duplicate_alerts(sessions, delta, total, accepted):
    seed(sessions)
    with sessions() as db:
        if db.bind.dialect.name != "postgresql":
            pytest.skip("Real row locks require PostgreSQL")
        usage.apply_usage_with_quota(db, db.get(Project, "prj_quota"), traces=70)
        db.commit()
    barrier = Barrier(4)

    def consume(_):
        with sessions() as db:
            project = db.get(Project, "prj_quota")
            counter = usage.get_or_create_counter(db, "org_quota", usage.current_period())
            usage.enforce_quota(db, project, "traces_ingested", delta)
            barrier.wait(timeout=10)
            try:
                usage.apply_usage_with_quota(db, project, traces=delta)
            except HTTPException as exc:
                assert exc.status_code == 402
                db.rollback()
                return False
            db.commit()
            assert counter.traces_ingested >= 75
            return True

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(consume, range(4))) == accepted
    with sessions() as db:
        assert db.query(UsageCounter).filter_by(organization_id="org_quota").one().traces_ingested == total
        assert db.query(Notification).count() == 2
