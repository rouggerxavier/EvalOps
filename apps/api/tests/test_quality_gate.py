from datetime import timedelta
import os
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.db import SessionLocal
from app.main import app
from app.models import (AuditLog, EvaluationRun, EvaluationScore, EvaluatorRow, Membership,
                        Organization, Project, QualityGateConfig, Rubric, RubricVersion, Span, Trace, User, utcnow)
from app.security import create_access_token

DEFAULTS = dict(min_score=0.8, max_ungrounded_rate=0.05, max_avg_cost_usd=0.05, max_p95_ms=2000, require_zero_critical=True)


@pytest.fixture
def gate():
    with SessionLocal() as db:
        db.add_all([User(id="owner", email="owner@gate.test", name="Owner"), User(id="outsider", email="outside@gate.test", name="Outside"),
                    Organization(id="org", name="Org", slug="org"), Organization(id="foreign", name="Foreign", slug="foreign")])
        db.flush()
        db.add_all([Membership(user_id="owner", organization_id="org", role="owner"),
                    Project(id="project", organization_id="org", name="Project", slug="project"),
                    Project(id="sibling", organization_id="org", name="Sibling", slug="sibling"),
                    Project(id="private", organization_id="foreign", name="Private", slug="private"),
                    Project(id="archived", organization_id="org", name="Archived", slug="archived", archived_at=utcnow())])
        db.commit()
    headers = {"Authorization": "Bearer " + create_access_token(sub="owner", email="owner@gate.test", name="Owner")}
    return TestClient(app), headers, "/v1/projects/project/quality-gate"


def trace(trace_id="t1", **overrides):
    now = utcnow()
    values = dict(id=trace_id, project_id="project", organization_id="org", name="agent.run", environment="prod", status="ok",
                  started_at=now, ended_at=now + timedelta(milliseconds=1000), duration_ms=1000, total_cost_usd=0.01, metadata_json={})
    with SessionLocal() as db:
        db.add(Trace(**{**values, **overrides}))
        db.commit()


def evaluation(*, score=0.9, critical_pass=True, version=1, run_status="completed", rules=True, metadata=None):
    with SessionLocal() as db:
        if not db.get(Rubric, "rb"):
            db.add(Rubric(id="rb", project_id="project", slug="safety", current_version=1, threshold=0.7))
            db.flush()
        spec = {"automatic_fail_conditions": [{"slug": "safety_violation", "evaluator_id": "safe"}] if rules else []}
        db.add(RubricVersion(id=f"rv{version}", rubric_id="rb", version=version, yaml_source="", parsed_spec=spec, created_by="owner"))
        db.flush()
        db.add(EvaluatorRow(id=f"e{version}", rubric_version_id=f"rv{version}", slug="safe", type="regex_match"))
        db.add(EvaluationRun(id=f"run{version}", project_id="project", trace_id="t1", rubric_id="rb", rubric_version=version,
                             triggered_by="test", status=run_status, aggregate_score=score, passed=critical_pass, run_metadata=metadata or {}))
        db.flush()
        db.add(EvaluationScore(id=f"s{version}", run_id=f"run{version}", evaluator_row_id=f"e{version}", evaluator_slug="safe",
                               score=1 if critical_pass else 0, passed=critical_pass, raw_output={}))
        db.commit()


def configure(gate, **overrides):
    client, headers, url = gate
    response = client.put(url, headers=headers, json={**DEFAULTS, **overrides})
    assert response.status_code == 200, response.text
    return response.json()


def status(gate, query=""):
    client, headers, url = gate
    response = client.get(url + "/status" + query, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def reason(body, metric):
    return next(item for item in body["reasons"] if item["metric"] == metric)


def test_defaults_are_read_only_and_empty_project_needs_review(gate):
    client, headers, url = gate
    assert client.get(url, headers=headers).json() == {**DEFAULTS, "project_id": "project", "configured": False, "updated_at": None}
    assert status(gate)["status"] == "review"
    with SessionLocal() as db:
        assert db.query(QualityGateConfig).count() == 0
    configure(gate)
    assert status(gate)["status"] == "review"
    assert status(gate)["metrics"]["avg_score"] is None


def test_configuration_persists_replaces_and_is_project_scoped(gate):
    values = configure(gate, min_score=0.85, max_ungrounded_rate=0.2, max_avg_cost_usd=0.002, max_p95_ms=500, require_zero_critical=False)
    client, headers, url = gate
    assert client.get(url, headers=headers).json() == values
    with SessionLocal() as db:
        assert db.get(QualityGateConfig, "project").min_score == 0.85
        assert db.query(AuditLog).filter_by(action="quality_gate.updated").count() == 1
    configure(gate)
    assert client.get(url, headers=headers).json()["min_score"] == 0.8
    assert client.get(url.replace("project/", "sibling/"), headers=headers).json()["configured"] is False
    with SessionLocal() as db:
        assert db.query(QualityGateConfig).count() == 1


@pytest.mark.parametrize("field,value", [("min_score", -0.1), ("min_score", 1.1), ("max_ungrounded_rate", -1), ("max_ungrounded_rate", 2),
    ("max_avg_cost_usd", -1), ("max_avg_cost_usd", "NaN"), ("max_avg_cost_usd", "Infinity"), ("max_p95_ms", -1),
    ("max_p95_ms", 1.5), ("max_p95_ms", 86400001), ("require_zero_critical", "false"), ("unknown_field", True)])
def test_invalid_configuration_is_rejected_without_persisting(gate, field, value):
    client, headers, url = gate
    assert client.put(url, headers=headers, json={**DEFAULTS, field: value}).status_code == 422
    with SessionLocal() as db:
        assert db.query(QualityGateConfig).count() == 0


def test_complete_evidence_passes_and_non_rag_is_not_applicable(gate):
    configure(gate)
    trace()
    evaluation()
    body = status(gate)
    assert body["status"] == "pass" and body["metrics"]["avg_score"] == 0.9
    assert body["metrics"]["critical_violations"] == 0
    assert reason(body, "ungrounded")["code"] == "not_applicable"


@pytest.mark.parametrize("overrides,metric", [({"min_score": 0.95}, "quality"), ({"max_avg_cost_usd": 0.005}, "avg_cost"), ({"max_p95_ms": 999}, "p95")])
def test_threshold_failures_have_structured_reasons(gate, overrides, metric):
    configure(gate, **overrides)
    trace()
    evaluation()
    body = status(gate)
    assert body["status"] == "fail"
    assert reason(body, metric)["code"] == "threshold_exceeded" and reason(body, metric)["sample_count"] == 1


def test_exact_thresholds_are_inclusive(gate):
    configure(gate, min_score=0.9, max_avg_cost_usd=0.01, max_p95_ms=1000)
    trace()
    evaluation()
    assert status(gate)["status"] == "pass"


def test_critical_violation_fails_even_when_average_quality_passes(gate):
    configure(gate)
    trace()
    evaluation(critical_pass=False)
    body = status(gate)
    assert body["status"] == "fail" and reason(body, "quality")["status"] == "pass"
    assert reason(body, "critical")["observed"] == 1
    configure(gate, require_zero_critical=False)
    assert status(gate)["status"] == "pass"


@pytest.mark.parametrize("run_status,metadata,rules", [("error", {}, True), ("running", {}, True), ("completed", {"partial_failure": True}, True), ("completed", {}, False)])
def test_failed_partial_or_unchecked_evidence_needs_review(gate, run_status, metadata, rules):
    configure(gate)
    trace()
    evaluation(run_status=run_status, metadata=metadata, rules=rules)
    assert status(gate)["status"] == "review"


def test_incomplete_coverage_needs_review_and_violation_takes_precedence(gate):
    configure(gate)
    trace()
    trace("unevaluated")
    evaluation()
    body = status(gate)
    assert body["status"] == "review" and reason(body, "quality")["code"] == "incomplete_evidence"
    configure(gate, max_avg_cost_usd=0)
    assert status(gate)["status"] == "fail"


def test_latest_rubric_attempt_replaces_old_failure_but_error_does_not_pass(gate):
    configure(gate)
    trace()
    evaluation(score=0.1, critical_pass=False)
    evaluation(score=0.95, version=2)
    assert status(gate)["status"] == "pass"
    evaluation(version=3, run_status="error")
    assert status(gate)["status"] == "review"


def test_grounding_reuses_claim_consolidation_and_counts_unknown_coverage(gate):
    configure(gate, require_zero_critical=False, max_ungrounded_rate=0.5)
    trace(metadata_json={"claims": [{"text": "A", "grounded": True}, {"text": "B", "grounded": False}], "pipeline_version": "1"})
    evaluation(rules=False)
    assert status(gate)["metrics"]["ungrounded_rate"] == 0.5 and status(gate)["status"] == "pass"
    configure(gate, require_zero_critical=False, max_ungrounded_rate=0.49)
    assert reason(status(gate), "ungrounded")["status"] == "fail"
    trace("unknown", name="rag.answer")
    configure(gate, require_zero_critical=False, max_ungrounded_rate=1)
    assert reason(status(gate), "ungrounded")["code"] == "incomplete_evidence"


def test_zero_support_rate_is_preserved_in_shared_rag_and_fails(gate):
    configure(gate, require_zero_critical=False)
    trace(metadata_json={"support_rate": 0, "quality_score": 0})
    evaluation(rules=False)
    client, headers, _ = gate
    rag = client.get("/v1/traces/t1/rag", headers=headers).json()
    assert rag["support_rate"] == 0 and rag["avg_score"] == 0
    assert status(gate)["metrics"]["ungrounded_rate"] == 1 and status(gate)["status"] == "fail"


def test_span_grounding_redacted_and_out_of_range_support_are_not_false_passes(gate):
    configure(gate, require_zero_critical=False)
    trace()
    evaluation(rules=False)
    with SessionLocal() as db:
        now = utcnow()
        db.add(Span(id="span", trace_id="t1", type="eval", name="rag.grounding.validate", status="ok", duration_ms=50,
                    started_at=now, ended_at=now, output={"support_rate": 1}))
        db.commit()
    assert status(gate)["status"] == "pass"
    with SessionLocal() as db:
        db.get(Trace, "t1").redacted = True
        db.commit()
    assert reason(status(gate), "ungrounded")["status"] == "review"
    with SessionLocal() as db:
        db.get(Trace, "t1").redacted = False
        db.get(Span, "span").output = {"support_rate": 2}
        db.commit()
    assert reason(status(gate), "ungrounded")["status"] == "review"


def test_scope_matches_overview_and_soft_deleted_data_is_excluded(gate):
    configure(gate, require_zero_critical=False)
    trace()
    evaluation(rules=False)
    trace("old", created_at=utcnow() - timedelta(days=2), duration_ms=9000, total_cost_usd=10)
    trace("staging", environment="staging", duration_ms=9000, total_cost_usd=10)
    trace("deleted", deleted_at=utcnow(), duration_ms=9000, total_cost_usd=10)
    trace("sibling", project_id="sibling", duration_ms=9000, total_cost_usd=10)
    body = status(gate, "?window=24h&environment=prod")
    assert body["status"] == "pass" and body["metrics"]["trace_count"] == 1
    client, headers, _ = gate
    overview = client.get("/v1/analytics/overview?project_id=project&window=24h&environment=prod", headers=headers).json()
    assert overview["kpis"]["latency_p95_ms"] == body["metrics"]["latency_p95_ms"]
    assert status(gate, "?window=7d&environment=prod")["status"] == "fail"
    assert status(gate, "?window=30d")["metrics"]["trace_count"] == 3


def test_p95_uses_nearest_rank_and_cost_is_per_trace(gate):
    configure(gate, require_zero_critical=False)
    for i in range(1, 21):
        trace(f"t{i}", duration_ms=i * 100, total_cost_usd=i * 0.001)
    body = status(gate)
    assert body["metrics"]["latency_p95_ms"] == 1900
    assert body["metrics"]["avg_cost_usd"] == pytest.approx(0.0105)


@pytest.mark.parametrize("target", ["private", "archived", "missing"])
def test_foreign_archived_missing_projects_cannot_be_read_or_modified(gate, target):
    client, headers, _ = gate
    url = f"/v1/projects/{target}/quality-gate"
    assert client.get(url, headers=headers).status_code == 404
    assert client.get(url + "/status", headers=headers).status_code == 404
    assert client.put(url, headers=headers, json=DEFAULTS).status_code == 404


def test_unauthenticated_outsider_and_ingest_key_cannot_access_gate(gate):
    client, headers, url = gate
    outsider = {"Authorization": "Bearer " + create_access_token(sub="outsider", email="outside@gate.test", name="Outside")}
    key = client.post("/v1/projects/project/api-keys", headers=headers, json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]}).json()["key"]
    for denied_headers, code in [({}, 401), (outsider, 404), ({"X-EvalOps-Key": key}, 401)]:
        assert client.get(url, headers=denied_headers).status_code == code
        assert client.get(url + "/status", headers=denied_headers).status_code == code
        assert client.put(url, headers=denied_headers, json=DEFAULTS).status_code == code


def test_invalid_window_is_rejected(gate):
    client, headers, url = gate
    assert client.get(url + "/status?window=all", headers=headers).status_code == 422


def test_quality_gate_migration_upgrade_and_rollback_preserve_projects(tmp_path):
    api_root = Path(__file__).resolve().parents[1]
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    env = {**os.environ, "DATABASE_URL": database_url}
    def migrate(revision, direction="upgrade"):
        subprocess.run([sys.executable, "-m", "alembic", direction, revision], cwd=api_root, env=env, check=True, capture_output=True)
    migrate("0008_export_jobs_file_size_bytes")
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO organizations (id,name,slug,created_at) VALUES ('org','Org','org',CURRENT_TIMESTAMP)"))
        conn.execute(text("INSERT INTO projects (id,organization_id,name,slug,default_environment,created_at) VALUES ('project','org','Project','project','prod',CURRENT_TIMESTAMP)"))
    migrate("head")
    assert "quality_gate_configs" in inspect(engine).get_table_names()
    migrate("0008_export_jobs_file_size_bytes", "downgrade")
    assert "quality_gate_configs" not in inspect(engine).get_table_names()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM projects WHERE id='project'")).scalar() == "Project"
    migrate("head")
    assert "quality_gate_configs" in inspect(engine).get_table_names()
    engine.dispose()


def test_unconfigured_limits_are_suggestions_and_never_fail_or_pass(gate):
    trace(total_cost_usd=10, duration_ms=20000)
    evaluation(critical_pass=False)
    body = status(gate)
    assert body["status"] == "review"
    assert all(item["status"] == "review" for item in body["reasons"])


@pytest.mark.parametrize("error_key", ["error", "parse_error", "schema_error"])
def test_evaluator_errors_are_missing_evidence_not_critical_violations(gate, error_key):
    configure(gate)
    trace()
    evaluation(critical_pass=False)
    with SessionLocal() as db:
        db.get(EvaluationScore, "s1").raw_output = {error_key: "evaluator_failed"}
        db.commit()
    body = status(gate)
    assert body["status"] == "review"
    assert body["metrics"]["critical_violations"] is None


def test_missing_individual_scores_cannot_approve_quality(gate):
    configure(gate, require_zero_critical=False)
    trace()
    evaluation(rules=False)
    with SessionLocal() as db:
        db.delete(db.get(EvaluationScore, "s1"))
        db.commit()
    assert reason(status(gate), "quality")["status"] == "review"


def test_flag_only_critical_condition_requires_review(gate):
    configure(gate)
    trace()
    evaluation()
    with SessionLocal() as db:
        db.get(RubricVersion, "rv1").parsed_spec = {"automatic_fail_conditions": [{"slug": "flag-only", "flag": "unsafe"}]}
        db.commit()
    assert reason(status(gate), "critical")["status"] == "review"
