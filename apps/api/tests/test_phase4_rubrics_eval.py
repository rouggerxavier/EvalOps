"""Phase 4 tests: rubric YAML parser, 7 evaluators, eval engine, and API endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import EvaluationRun, User
from app.security import create_access_token

client = TestClient(app)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _auth(user_id: str = "usr_1", email: str = "u@example.com") -> dict:
    token = create_access_token(sub=user_id, email=email, name="Tester")
    return {"Authorization": f"Bearer {token}"}


def _bootstrap() -> tuple[dict, str, str, str]:
    """Create user, org, project. Returns (headers, org_id, project_id, api_key)."""
    with SessionLocal() as db:
        db.add(User(id="usr_1", email="u@example.com", name="Tester"))
        db.commit()
    headers = _auth()
    org = client.post("/v1/organizations", headers=headers, json={"name": "Acme", "slug": "acme"}).json()
    project = client.post(
        "/v1/projects",
        headers=headers,
        json={"organization_id": org["id"], "name": "P1", "slug": "p1"},
    ).json()
    key_resp = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "ingest", "environment": "prod", "scopes": ["ingest", "read"]},
    ).json()
    return headers, org["id"], project["id"], key_resp["key"]


def _ingest_trace(api_key: str, project_id: str) -> str:
    """Ingest a simple trace with llm_call span. Returns trace_id."""
    now = datetime.now(timezone.utc)
    resp = client.post(
        "/v1/traces",
        headers={"X-EvalOps-Key": api_key},
        json={
            "traces": [
                {
                    "client_trace_id": "ct_eval_test",
                    "name": "test.trace",
                    "service": "svc",
                    "environment": "prod",
                    "started_at": now.isoformat(),
                    "ended_at": (now + timedelta(seconds=1)).isoformat(),
                    "status": "ok",
                    "tags": {},
                    "spans": [
                        {
                            "client_span_id": "cs_1",
                            "type": "llm_call",
                            "name": "openai.chat",
                            "started_at": now.isoformat(),
                            "ended_at": (now + timedelta(milliseconds=800)).isoformat(),
                            "status": "ok",
                            "provider": "openai",
                            "model": "gpt-4o-mini",
                            "tokens_in": 50,
                            "tokens_out": 30,
                            "messages_in": [{"role": "user", "content": "What is the capital of France?"}],
                            "messages_out": [{"role": "assistant", "content": "The capital of France is Paris."}],
                        }
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["results"][0]["trace_id"]


MINIMAL_RUBRIC = """
slug: test-rubric
name: Test Rubric
description: A minimal test rubric
threshold: 0.5
aggregate: weighted_mean
evaluators:
  - id: length_check
    type: length_bounds
    weight: 1.0
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 5
      max: 500
"""


# ── Parser tests ──────────────────────────────────────────────────────────────

class TestRubricParser:
    def test_valid_minimal_yaml(self):
        from app.domain.rubrics.parser import parse_rubric_yaml
        spec = parse_rubric_yaml(MINIMAL_RUBRIC)
        assert spec.slug == "test-rubric"
        assert spec.threshold == 0.5
        assert len(spec.evaluators) == 1

    def test_invalid_yaml_syntax(self):
        from app.domain.rubrics.parser import parse_rubric_yaml
        with pytest.raises(ValueError, match="YAML parse error"):
            parse_rubric_yaml("slug: [\nbroken")

    def test_missing_required_fields(self):
        from app.domain.rubrics.parser import parse_rubric_yaml
        with pytest.raises(ValueError):
            parse_rubric_yaml("slug: x\nname: X\ndescription: D\nthreshold: 0.5\naggregate: mean")
        # Missing evaluators

    def test_unknown_top_level_field_rejected(self):
        from app.domain.rubrics.parser import parse_rubric_yaml
        yaml_src = MINIMAL_RUBRIC + "\nunknown_field: oops\n"
        with pytest.raises(ValueError, match="unknown top-level fields"):
            parse_rubric_yaml(yaml_src)

    def test_invalid_evaluator_type(self):
        from app.domain.rubrics.parser import parse_rubric_yaml
        yaml_src = """
slug: x
name: X
description: D
threshold: 0.5
aggregate: mean
evaluators:
  - id: e1
    type: custom_python
    weight: 1.0
    config: {}
"""
        with pytest.raises(ValueError, match="unknown evaluator type"):
            parse_rubric_yaml(yaml_src)

    def test_duplicate_evaluator_ids_rejected(self):
        from app.domain.rubrics.parser import parse_rubric_yaml
        yaml_src = """
slug: x
name: X
description: D
threshold: 0.5
aggregate: mean
evaluators:
  - id: dup
    type: length_bounds
    weight: 1.0
    config: {target: trace.output.assistant_message, min: 1}
  - id: dup
    type: length_bounds
    weight: 1.0
    config: {target: trace.output.assistant_message, min: 1}
"""
        with pytest.raises(ValueError, match="duplicate evaluator id"):
            parse_rubric_yaml(yaml_src)

    def test_invalid_slug_format(self):
        from app.domain.rubrics.parser import parse_rubric_yaml
        yaml_src = MINIMAL_RUBRIC.replace("slug: test-rubric", "slug: Test Rubric!")
        with pytest.raises(ValueError):
            parse_rubric_yaml(yaml_src)

    def test_version_n_plus_1(self):
        """New version creates version n+1 and is immutable."""
        headers, _, project_id, api_key = _bootstrap()
        r1 = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": MINIMAL_RUBRIC},
        )
        assert r1.status_code == 201
        rubric_id = r1.json()["rubric"]["id"]
        assert r1.json()["version"]["version"] == 1

        r2 = client.post(
            f"/v1/rubrics/{rubric_id}/versions",
            headers=headers,
            json={"yaml_source": MINIMAL_RUBRIC},
        )
        assert r2.status_code == 201
        assert r2.json()["rubric_version"] == 2


# ── Evaluator unit tests ──────────────────────────────────────────────────────

CONTEXT = {
    "trace": {
        "output": {"assistant_message": "The capital of France is Paris.", "text": "The capital of France is Paris."},
        "input": {"user_message": "What is the capital?", "text": "What is the capital?"},
    }
}


class TestRegexMatch:
    def test_must_match_passes(self):
        from app.domain.evaluators.regex_match import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "pattern": "Paris", "mode": "must_match"})
        assert result.score == 1.0
        assert result.passed is True

    def test_must_match_fails(self):
        from app.domain.evaluators.regex_match import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "pattern": "Berlin", "mode": "must_match"})
        assert result.score == 0.0
        assert result.passed is False

    def test_must_not_match_passes(self):
        from app.domain.evaluators.regex_match import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "pattern": "\\bCPF\\b", "mode": "must_not_match"})
        assert result.passed is True

    def test_must_not_match_fails(self):
        from app.domain.evaluators.regex_match import run
        ctx = {"trace": {"output": {"assistant_message": "CPF: 123.456.789-00"}}}
        result = run(ctx, {"target": "trace.output.assistant_message", "pattern": "\\bCPF\\b", "mode": "must_not_match"})
        assert result.passed is False

    def test_case_insensitive_flag(self):
        from app.domain.evaluators.regex_match import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "pattern": "paris", "mode": "must_match", "flags": ["i"]})
        assert result.passed is True


class TestKeywordPresence:
    def test_any_require_passes(self):
        from app.domain.evaluators.keyword_presence import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "keywords": ["Paris", "London"], "require": "any"})
        assert result.passed is True
        assert result.score == 1.0

    def test_all_require_partial_score(self):
        from app.domain.evaluators.keyword_presence import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "keywords": ["Paris", "Berlin"], "require": "all"})
        assert result.passed is False
        assert result.score == pytest.approx(0.5)

    def test_all_require_full_score(self):
        from app.domain.evaluators.keyword_presence import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "keywords": ["Paris", "France"], "require": "all"})
        assert result.passed is True
        assert result.score == 1.0

    def test_none_require_passes(self):
        from app.domain.evaluators.keyword_presence import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "keywords": ["Berlin"], "require": "none"})
        assert result.passed is True

    def test_none_require_fails(self):
        from app.domain.evaluators.keyword_presence import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "keywords": ["Paris"], "require": "none"})
        assert result.passed is False


class TestLengthBounds:
    def test_within_bounds(self):
        from app.domain.evaluators.length_bounds import run
        result = run(CONTEXT, {"target": "trace.output.assistant_message", "unit": "chars", "min": 5, "max": 500})
        assert result.passed is True
        assert result.score == 1.0

    def test_below_min(self):
        from app.domain.evaluators.length_bounds import run
        ctx = {"trace": {"output": {"assistant_message": "Hi"}}}
        result = run(ctx, {"target": "trace.output.assistant_message", "unit": "chars", "min": 100})
        assert result.passed is False
        assert 0.0 <= result.score < 1.0

    def test_above_max(self):
        from app.domain.evaluators.length_bounds import run
        ctx = {"trace": {"output": {"assistant_message": "word " * 500}}}
        result = run(ctx, {"target": "trace.output.assistant_message", "unit": "words", "max": 10})
        assert result.passed is False

    def test_words_unit(self):
        from app.domain.evaluators.length_bounds import run
        ctx = {"trace": {"output": {"assistant_message": "one two three four five"}}}
        result = run(ctx, {"target": "trace.output.assistant_message", "unit": "words", "min": 3, "max": 10})
        assert result.passed is True


class TestJsonSchemaValid:
    def test_valid_json(self):
        from app.domain.evaluators.json_schema_valid import run
        ctx = {"trace": {"output": {"assistant_message": '{"score": 0.9, "reasoning": "good"}'}}}
        result = run(ctx, {
            "target": "trace.output.assistant_message",
            "schema": {"type": "object", "properties": {"score": {"type": "number"}}, "required": ["score"]},
        })
        assert result.passed is True

    def test_invalid_json(self):
        from app.domain.evaluators.json_schema_valid import run
        ctx = {"trace": {"output": {"assistant_message": "not json"}}}
        result = run(ctx, {"target": "trace.output.assistant_message"})
        assert result.passed is False

    def test_extract_first_mode(self):
        from app.domain.evaluators.json_schema_valid import run
        ctx = {"trace": {"output": {"assistant_message": 'Here is the result: {"score": 0.8} done.'}}}
        result = run(ctx, {"target": "trace.output.assistant_message", "parse_mode": "extract_first"})
        assert result.passed is True

    def test_schema_violation(self):
        from app.domain.evaluators.json_schema_valid import run
        ctx = {"trace": {"output": {"assistant_message": '{"score": "not_a_number"}'}}}
        result = run(ctx, {
            "target": "trace.output.assistant_message",
            "schema": {"type": "object", "properties": {"score": {"type": "number"}}, "required": ["score"]},
        })
        assert result.passed is False


class TestExactMatch:
    def test_exact_match_passes(self):
        from app.domain.evaluators.exact_match import run
        ctx = {"trace": {"output": {"assistant_message": "Paris"}}}
        result = run(ctx, {"target": "trace.output.assistant_message", "expected": "Paris"})
        assert result.passed is True

    def test_exact_match_fails(self):
        from app.domain.evaluators.exact_match import run
        ctx = {"trace": {"output": {"assistant_message": "Paris"}}}
        result = run(ctx, {"target": "trace.output.assistant_message", "expected": "Berlin"})
        assert result.passed is False

    def test_normalize_lowercase_strip(self):
        from app.domain.evaluators.exact_match import run
        ctx = {"trace": {"output": {"assistant_message": "  PARIS  "}}}
        result = run(ctx, {
            "target": "trace.output.assistant_message",
            "expected": "paris",
            "normalize": ["lowercase", "strip"],
        })
        assert result.passed is True


class TestCosineSimilarity:
    def test_cosine_mock(self, monkeypatch):
        import app.domain.evaluators.cosine_similarity as cs_mod
        call_count = {"n": 0}
        def mock_embed(text, provider, model):
            call_count["n"] += 1
            # Return identical vectors → similarity = 1.0
            return [1.0, 0.0, 0.0]
        monkeypatch.setattr(cs_mod, "get_embedding", mock_embed)

        from app.domain.evaluators.cosine_similarity import run
        ctx = {
            "trace": {"output": {"assistant_message": "Paris"}},
            "expected": {"assistant_message": "Paris"},
        }
        result = run(ctx, {
            "target_a": "trace.output.assistant_message",
            "target_b": "Paris",
            "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
            "pass_threshold": 0.9,
        })
        assert result.passed is True
        assert result.score == pytest.approx(1.0)

    def test_cosine_low_similarity(self, monkeypatch):
        import app.domain.evaluators.cosine_similarity as cs_mod
        vectors = [[1.0, 0.0], [0.0, 1.0]]
        idx = {"i": 0}
        def mock_embed(text, provider, model):
            v = vectors[idx["i"] % 2]
            idx["i"] += 1
            return v
        monkeypatch.setattr(cs_mod, "get_embedding", mock_embed)

        from app.domain.evaluators.cosine_similarity import run
        result = run(CONTEXT, {
            "target_a": "trace.output.assistant_message",
            "target_b": "something else",
            "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
            "pass_threshold": 0.9,
        })
        assert result.passed is False
        assert result.score == pytest.approx(0.0)


class TestLlmJudge:
    def test_valid_response(self, monkeypatch):
        import app.domain.evaluators.llm_judge as lj_mod
        monkeypatch.setattr(lj_mod, "call_llm", lambda model, messages, temp: '{"score": 0.85, "reasoning": "Good answer"}')

        from app.domain.evaluators.llm_judge import run
        result = run(CONTEXT, {
            "model": "openai/gpt-4o-mini",
            "prompt": "Rate the answer: {{ trace.output.assistant_message }}",
            "pass_threshold": 0.7,
        })
        assert result.passed is True
        assert result.score == pytest.approx(0.85)
        assert "Good answer" in result.reasoning

    def test_invalid_json_retry(self, monkeypatch):
        import app.domain.evaluators.llm_judge as lj_mod
        calls = {"n": 0}
        def flaky_llm(model, messages, temp):
            calls["n"] += 1
            if calls["n"] == 1:
                return "not valid json at all"
            return '{"score": 0.75, "reasoning": "ok"}'
        monkeypatch.setattr(lj_mod, "call_llm", flaky_llm)

        from app.domain.evaluators.llm_judge import run
        result = run(CONTEXT, {
            "model": "openai/gpt-4o-mini",
            "prompt": "Rate: {{ trace.output.assistant_message }}",
            "retry_on_invalid": 1,
            "pass_threshold": 0.7,
        })
        assert result.passed is True
        assert calls["n"] == 2  # retried once

    def test_all_retries_exhausted_returns_failed(self, monkeypatch):
        import app.domain.evaluators.llm_judge as lj_mod
        monkeypatch.setattr(lj_mod, "call_llm", lambda *a, **kw: "garbage response")

        from app.domain.evaluators.llm_judge import run
        result = run(CONTEXT, {
            "model": "openai/gpt-4o-mini",
            "prompt": "Rate: {{ trace.output.assistant_message }}",
            "retry_on_invalid": 1,
            "pass_threshold": 0.7,
        })
        assert result.passed is False
        assert result.raw_output.get("parse_error") is True

    def test_low_score_fails_threshold(self, monkeypatch):
        import app.domain.evaluators.llm_judge as lj_mod
        monkeypatch.setattr(lj_mod, "call_llm", lambda *a, **kw: '{"score": 0.4, "reasoning": "bad"}')

        from app.domain.evaluators.llm_judge import run
        result = run(CONTEXT, {"model": "openai/gpt-4o-mini", "prompt": "x", "pass_threshold": 0.7})
        assert result.passed is False
        assert result.score == pytest.approx(0.4)


# ── Aggregation tests ─────────────────────────────────────────────────────────

class TestAggregation:
    def test_weighted_mean(self):
        from app.domain.services.eval_service import _aggregate
        scores = [(0.8, 2.0), (0.4, 1.0)]
        result = _aggregate(scores, "weighted_mean")
        assert result == pytest.approx((0.8 * 2 + 0.4 * 1) / 3)

    def test_mean(self):
        from app.domain.services.eval_service import _aggregate
        scores = [(0.6, 1.0), (0.8, 1.0)]
        assert _aggregate(scores, "mean") == pytest.approx(0.7)

    def test_min(self):
        from app.domain.services.eval_service import _aggregate
        scores = [(0.9, 1.0), (0.3, 1.0), (0.7, 1.0)]
        assert _aggregate(scores, "min") == pytest.approx(0.3)

    def test_max(self):
        from app.domain.services.eval_service import _aggregate
        scores = [(0.9, 1.0), (0.3, 1.0)]
        assert _aggregate(scores, "max") == pytest.approx(0.9)

    def test_empty_scores_returns_zero(self):
        from app.domain.services.eval_service import _aggregate
        assert _aggregate([], "weighted_mean") == 0.0


# ── End-to-end evaluation API tests ──────────────────────────────────────────

class TestEvalAPI:
    def test_create_rubric_and_run_evaluation(self):
        headers, _, project_id, api_key = _bootstrap()
        trace_id = _ingest_trace(api_key, project_id)

        r = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": MINIMAL_RUBRIC},
        )
        assert r.status_code == 201, r.text
        rubric_id = r.json()["rubric"]["id"]

        run_r = client.post(
            "/v1/evaluations/run",
            headers=headers,
            json={"trace_id": trace_id, "rubric_id": rubric_id},
        )
        assert run_r.status_code == 201, run_r.text
        run_data = run_r.json()["run"]
        assert run_data["status"] == "completed"
        assert run_data["passed"] is True
        assert len(run_data["scores"]) == 1
        assert run_data["scores"][0]["evaluator_slug"] == "length_check"

    def test_invalid_yaml_returns_422(self):
        headers, _, project_id, _ = _bootstrap()
        r = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": "slug: [\nbroken yaml"},
        )
        assert r.status_code == 422

    def test_unknown_top_level_field_returns_422(self):
        headers, _, project_id, _ = _bootstrap()
        r = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": MINIMAL_RUBRIC + "\nforbidden_field: oops"},
        )
        assert r.status_code == 422

    def test_list_trace_evaluations(self):
        headers, _, project_id, api_key = _bootstrap()
        trace_id = _ingest_trace(api_key, project_id)
        r_rub = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": MINIMAL_RUBRIC},
        )
        rubric_id = r_rub.json()["rubric"]["id"]
        client.post("/v1/evaluations/run", headers=headers, json={"trace_id": trace_id, "rubric_id": rubric_id})

        r = client.get(f"/v1/traces/{trace_id}/evaluations", headers=headers)
        assert r.status_code == 200
        assert len(r.json()["data"]) == 1

    def test_get_evaluation_run(self):
        headers, _, project_id, api_key = _bootstrap()
        trace_id = _ingest_trace(api_key, project_id)
        r_rub = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": MINIMAL_RUBRIC},
        )
        rubric_id = r_rub.json()["rubric"]["id"]
        run_id = client.post(
            "/v1/evaluations/run",
            headers=headers,
            json={"trace_id": trace_id, "rubric_id": rubric_id},
        ).json()["run"]["id"]

        r = client.get(f"/v1/evaluations/{run_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["run"]["id"] == run_id

    def test_rubric_slug_conflict_returns_409(self):
        headers, _, project_id, _ = _bootstrap()
        client.post(f"/v1/projects/{project_id}/rubrics", headers=headers, json={"yaml_source": MINIMAL_RUBRIC})
        r2 = client.post(f"/v1/projects/{project_id}/rubrics", headers=headers, json={"yaml_source": MINIMAL_RUBRIC})
        assert r2.status_code == 409

    def test_list_rubric_versions(self):
        headers, _, project_id, _ = _bootstrap()
        r = client.post(f"/v1/projects/{project_id}/rubrics", headers=headers, json={"yaml_source": MINIMAL_RUBRIC})
        rubric_id = r.json()["rubric"]["id"]
        client.post(f"/v1/rubrics/{rubric_id}/versions", headers=headers, json={"yaml_source": MINIMAL_RUBRIC})

        vers = client.get(f"/v1/rubrics/{rubric_id}/versions", headers=headers)
        assert vers.status_code == 200
        assert len(vers.json()["data"]) == 2

    def test_cross_project_eval_forbidden(self):
        """Rubric from project A cannot evaluate trace from project B."""
        with SessionLocal() as db:
            db.add(User(id="usr_2", email="u2@example.com", name="User2"))
            db.commit()

        headers, _, project_id, api_key = _bootstrap()
        trace_id = _ingest_trace(api_key, project_id)

        # Create second org+project
        headers2 = _auth("usr_2", "u2@example.com")
        org2 = client.post("/v1/organizations", headers=headers2, json={"name": "Org2", "slug": "org2"}).json()
        proj2 = client.post(
            "/v1/projects",
            headers=headers2,
            json={"organization_id": org2["id"], "name": "P2", "slug": "p2"},
        ).json()
        r_rub2 = client.post(
            f"/v1/projects/{proj2['id']}/rubrics",
            headers=headers2,
            json={"yaml_source": MINIMAL_RUBRIC},
        )
        rubric2_id = r_rub2.json()["rubric"]["id"]

        # Try to evaluate trace from project 1 with rubric from project 2
        run_r = client.post(
            "/v1/evaluations/run",
            headers=headers,
            json={"trace_id": trace_id, "rubric_id": rubric2_id},
        )
        assert run_r.status_code == 403


class TestFailFastAndAutoFail:
    def test_fail_fast_stops_remaining_evaluators(self):
        """When fail_fast evaluator fails, subsequent evaluators should not run."""
        yaml_src = """
slug: fail-fast-rubric
name: FailFast Test
description: Tests fail_fast behavior
threshold: 0.5
aggregate: mean
evaluators:
  - id: must_contain_paris
    type: regex_match
    weight: 1.0
    fail_fast: true
    config:
      target: trace.output.assistant_message
      pattern: "NOTPRESENT"
      mode: must_match
  - id: length_ok
    type: length_bounds
    weight: 1.0
    config:
      target: trace.output.assistant_message
      unit: chars
      min: 1
"""
        headers, _, project_id, api_key = _bootstrap()
        trace_id = _ingest_trace(api_key, project_id)

        r_rub = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": yaml_src},
        )
        assert r_rub.status_code == 201, r_rub.text
        rubric_id = r_rub.json()["rubric"]["id"]

        run_r = client.post(
            "/v1/evaluations/run",
            headers=headers,
            json={"trace_id": trace_id, "rubric_id": rubric_id},
        )
        assert run_r.status_code == 201
        run_data = run_r.json()["run"]
        # Only 1 score should exist (second evaluator was skipped)
        assert len(run_data["scores"]) == 1
        assert run_data["scores"][0]["evaluator_slug"] == "must_contain_paris"

    def test_auto_fail_forces_passed_false(self, monkeypatch):
        """auto_fail condition should set passed=False even if aggregate score passes threshold."""
        import app.domain.evaluators.llm_judge as lj_mod
        monkeypatch.setattr(lj_mod, "call_llm", lambda *a, **kw: '{"score": 0.9, "reasoning": "great"}')

        yaml_src = """
slug: auto-fail-rubric
name: AutoFail Test
description: Tests auto_fail behavior
threshold: 0.5
aggregate: mean
automatic_fail_conditions:
  - slug: no_pii
    evaluator_id: pii_check
    description: PII detected
evaluators:
  - id: pii_check
    type: regex_match
    weight: 1.0
    config:
      target: trace.output.assistant_message
      pattern: "Paris"
      mode: must_not_match
  - id: quality
    type: llm_judge
    weight: 1.0
    config:
      model: openai/gpt-4o-mini
      prompt: "Rate: {{ trace.output.assistant_message }}"
      pass_threshold: 0.5
"""
        headers, _, project_id, api_key = _bootstrap()
        trace_id = _ingest_trace(api_key, project_id)

        r_rub = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": yaml_src},
        )
        assert r_rub.status_code == 201, r_rub.text
        rubric_id = r_rub.json()["rubric"]["id"]

        run_r = client.post(
            "/v1/evaluations/run",
            headers=headers,
            json={"trace_id": trace_id, "rubric_id": rubric_id},
        )
        assert run_r.status_code == 201
        run_data = run_r.json()["run"]
        # Even though llm_judge gave 0.9, pii_check fails → auto_fail → passed=False
        assert run_data["passed"] is False


class TestBudgetExhausted:
    def test_judge_budget_exhausted(self, monkeypatch):
        """When monthly judge budget is exhausted, llm_judge creates error score."""
        import app.domain.services.eval_service as svc
        # Override budget check to always return False (exhausted)
        monkeypatch.setattr(svc, "_check_judge_budget", lambda *a, **kw: False)

        yaml_src = """
slug: budget-rubric
name: Budget Test
description: Tests budget exhaustion
threshold: 0.5
aggregate: mean
evaluators:
  - id: judge
    type: llm_judge
    weight: 1.0
    config:
      model: openai/gpt-4o-mini
      prompt: "Rate: {{ trace.output.assistant_message }}"
      pass_threshold: 0.7
"""
        headers, _, project_id, api_key = _bootstrap()
        trace_id = _ingest_trace(api_key, project_id)

        r_rub = client.post(
            f"/v1/projects/{project_id}/rubrics",
            headers=headers,
            json={"yaml_source": yaml_src},
        )
        rubric_id = r_rub.json()["rubric"]["id"]

        run_r = client.post(
            "/v1/evaluations/run",
            headers=headers,
            json={"trace_id": trace_id, "rubric_id": rubric_id},
        )
        assert run_r.status_code == 201
        run_data = run_r.json()["run"]
        # Score was created with error
        assert len(run_data["scores"]) == 1
        assert run_data["scores"][0]["reasoning"] == "judge_budget_exhausted"


def _ingest_named(api_key: str, client_trace_id: str) -> str:
    now = datetime.now(timezone.utc)
    resp = client.post(
        "/v1/traces",
        headers={"X-EvalOps-Key": api_key},
        json={
            "traces": [
                {
                    "client_trace_id": client_trace_id,
                    "name": "test.trace",
                    "environment": "prod",
                    "started_at": now.isoformat(),
                    "ended_at": (now + timedelta(seconds=1)).isoformat(),
                    "status": "ok",
                    "tags": {},
                    "spans": [
                        {
                            "client_span_id": "cs_1",
                            "type": "llm_call",
                            "name": "openai.chat",
                            "started_at": now.isoformat(),
                            "ended_at": (now + timedelta(milliseconds=800)).isoformat(),
                            "status": "ok",
                            "provider": "openai",
                            "model": "gpt-4o-mini",
                            "messages_in": [{"role": "user", "content": "What is the capital of France?"}],
                            "messages_out": [{"role": "assistant", "content": "The capital of France is Paris."}],
                        }
                    ],
                }
            ]
        },
    )
    assert resp.status_code == 202, resp.text
    return resp.json()["results"][0]["trace_id"]


def test_list_project_evaluations_excludes_soft_deleted_trace() -> None:
    headers, _, project_id, api_key = _bootstrap()
    active = _ingest_named(api_key, "ct_eval_active")
    deleted = _ingest_named(api_key, "ct_eval_deleted")

    rubric_id = client.post(
        f"/v1/projects/{project_id}/rubrics",
        headers=headers,
        json={"yaml_source": MINIMAL_RUBRIC},
    ).json()["rubric"]["id"]

    run_active = client.post(
        "/v1/evaluations/run", headers=headers,
        json={"trace_id": active, "rubric_id": rubric_id},
    ).json()["run"]["id"]
    run_deleted = client.post(
        "/v1/evaluations/run", headers=headers,
        json={"trace_id": deleted, "rubric_id": rubric_id},
    ).json()["run"]["id"]

    assert client.delete(f"/v1/traces/{deleted}", headers=headers).status_code == 204

    listed = client.get(f"/v1/projects/{project_id}/evaluations", headers=headers)
    assert listed.status_code == 200, listed.text
    run_ids = [r["id"] for r in listed.json()["data"]]
    assert run_active in run_ids
    assert run_deleted not in run_ids

    # Old run row is NOT deleted, only filtered from the project listing.
    with SessionLocal() as db:
        assert db.get(EvaluationRun, run_deleted) is not None


# ── Fix-7B.5 (A-08): cost_cap_usd is real + judge cost is recorded ───────────

class TestLlmJudgeCostCap:
    def test_cost_cap_blocks_before_spending_when_estimate_exceeds(self, monkeypatch):
        """A tiny cap must block the call entirely — call_llm never runs."""
        import app.domain.evaluators.llm_judge as lj_mod

        def _must_not_call(*a, **kw):
            raise AssertionError("call_llm invoked despite cost cap")

        monkeypatch.setattr(lj_mod, "call_llm", _must_not_call)
        from app.domain.evaluators.llm_judge import run

        result = run(CONTEXT, {
            "model": "openai/gpt-4o-mini",
            "prompt": "Rate: {{ trace.output.assistant_message }}",
            "cost_cap_usd": 1e-9,
        })
        assert result.passed is False
        assert result.reasoning == "cost_cap_exceeded"
        assert result.raw_output["error"] == "cost_cap_exceeded"
        assert result.cost_usd > 0  # estimated cost recorded for observability

    def test_cost_cap_allows_when_estimate_within_cap(self, monkeypatch):
        import app.domain.evaluators.llm_judge as lj_mod
        monkeypatch.setattr(
            lj_mod, "call_llm",
            lambda *a, **kw: '{"score": 0.85, "reasoning": "ok"}',
        )
        from app.domain.evaluators.llm_judge import run

        result = run(CONTEXT, {
            "model": "openai/gpt-4o-mini",
            "prompt": "Rate: {{ trace.output.assistant_message }}",
            "cost_cap_usd": 1.0,
        })
        assert result.passed is True
        assert result.score == pytest.approx(0.85)
        assert result.cost_usd > 0  # judge cost is no longer a dead 0.0

    def test_cost_cap_error_does_not_leak_internals(self, monkeypatch):
        import app.domain.evaluators.llm_judge as lj_mod
        monkeypatch.setattr(
            lj_mod, "call_llm",
            lambda *a, **kw: (_ for _ in ()).throw(AssertionError("nope")),
        )
        from app.domain.evaluators.llm_judge import run

        result = run(CONTEXT, {
            "model": "openai/gpt-4o-mini",
            "prompt": "Rate: {{ trace.output.assistant_message }}",
            "cost_cap_usd": 1e-12,
        })
        blob = f"{result.reasoning} {result.raw_output}"
        for leak in ("Traceback", "SELECT", "sqlite", "Bearer", "/home/", "\wsl", "OPENAI_API_KEY"):
            assert leak not in blob
        assert set(result.raw_output) == {"error", "estimated_cost_usd", "cost_cap_usd"}


JUDGE_COST_RUBRIC = """
slug: judge-cost-rubric
name: Judge Cost Rubric
description: llm_judge with a generous cap
threshold: 0.5
aggregate: mean
evaluators:
  - id: judge
    type: llm_judge
    weight: 1.0
    config:
      model: openai/gpt-4o-mini
      prompt: "Rate: {{ trace.output.assistant_message }}"
      pass_threshold: 0.5
      cost_cap_usd: 1.0
"""


def test_llm_judge_records_cost_usd_on_evaluation_run(monkeypatch):
    """EvaluationRun.cost_usd must reflect the judge cost (was always 0.0)."""
    import app.domain.evaluators.llm_judge as lj_mod
    monkeypatch.setattr(
        lj_mod, "call_llm",
        lambda *a, **kw: '{"score": 0.9, "reasoning": "great"}',
    )

    headers, _, project_id, api_key = _bootstrap()
    trace_id = _ingest_trace(api_key, project_id)
    rubric_id = client.post(
        f"/v1/projects/{project_id}/rubrics",
        headers=headers,
        json={"yaml_source": JUDGE_COST_RUBRIC},
    ).json()["rubric"]["id"]

    run_r = client.post(
        "/v1/evaluations/run",
        headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id},
    )
    assert run_r.status_code == 201, run_r.text
    run_data = run_r.json()["run"]
    assert float(run_data["cost_usd"]) > 0.0
    assert float(run_data["scores"][0]["cost_usd"]) > 0.0


def test_duplicate_llm_judge_evaluation_still_returns_409(monkeypatch):
    """Fix-7B.5 must not regress the G-11 duplicate-run 409 contract."""
    import app.domain.evaluators.llm_judge as lj_mod
    monkeypatch.setattr(
        lj_mod, "call_llm",
        lambda *a, **kw: '{"score": 0.9, "reasoning": "great"}',
    )
    headers, _, project_id, api_key = _bootstrap()
    trace_id = _ingest_trace(api_key, project_id)
    rubric_id = client.post(
        f"/v1/projects/{project_id}/rubrics",
        headers=headers,
        json={"yaml_source": JUDGE_COST_RUBRIC},
    ).json()["rubric"]["id"]

    first = client.post(
        "/v1/evaluations/run", headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id},
    )
    assert first.status_code == 201, first.text
    dup = client.post(
        "/v1/evaluations/run", headers=headers,
        json={"trace_id": trace_id, "rubric_id": rubric_id},
    )
    assert dup.status_code == 409
    assert dup.json()["detail"]["error"] == "evaluation_run_duplicate"
