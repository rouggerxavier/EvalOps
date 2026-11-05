"""Regressions for the P1 findings in docs/audits/auditoria-codigo-2026-11-05.md."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.domain.evaluators import llm_judge
from app.domain.services import eval_service
from app.infra.llm.pricing import compute_cost_usd
from app.main import app
from app.models import EvaluationRun, Membership, Notification, Organization, Project, User
from app.security import create_access_token, new_id
from app.workers.evaluation_worker import _evaluate
from app.workers.queue import get_arq_pool

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.pop(get_arq_pool, None)
    Base.metadata.drop_all(bind=engine)


class Workspace:
    def __init__(self, slug: str = "org-a", org_id: str | None = None) -> None:
        self.user_id, self.project_id = new_id("usr"), new_id("prj")
        self.org_id = org_id or new_id("org")
        with SessionLocal() as db:
            db.add(User(id=self.user_id, email=f"{slug}-{self.project_id}@example.com", name="Audit"))
            if org_id is None:
                db.add(Organization(id=self.org_id, name=slug, slug=slug))
            db.flush()
            db.add(Membership(user_id=self.user_id, organization_id=self.org_id, role="owner"))
            db.add(Project(id=self.project_id, organization_id=self.org_id, name=slug, slug=f"{slug}-{self.project_id[-6:]}"))
            db.commit()
        token = create_access_token(sub=self.user_id, email="a@example.com", name="Audit")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.key = self.create_key(["ingest", "read"])

    def create_key(self, scopes: list[str]) -> str:
        response = client.post(
            f"/v1/projects/{self.project_id}/api-keys",
            headers=self.headers,
            json={"name": "chave", "environment": "dev", "scopes": scopes},
        )
        assert response.status_code == 201, response.text
        return response.json()["key"]

    def ingest(self, answer: str | None = "resposta boa", user: str = "oi", offset_s: int = 0, **trace_fields) -> str:
        start = datetime.now(timezone.utc) - timedelta(hours=1) + timedelta(seconds=offset_s)
        end = (start + timedelta(seconds=1)).isoformat()
        span = {
            "client_span_id": "s1", "type": "llm_call", "name": "llm", "status": "ok",
            "started_at": start.isoformat(), "ended_at": end,
            "messages_in": [{"role": "user", "content": user}],
        }
        if answer is not None:
            span["messages_out"] = [{"role": "assistant", "content": answer}]
        trace = {
            "client_trace_id": new_id("ct"), "name": "turno", "environment": "dev", "status": "ok",
            "started_at": start.isoformat(), "ended_at": end, "spans": [span], **trace_fields,
        }
        response = client.post("/v1/traces", headers={"X-EvalOps-Key": self.key}, json={"traces": [trace]})
        assert response.status_code == 202 and response.json()["errors"] == [], response.text
        return response.json()["results"][0]["trace_id"]

    def rubric(self, yaml_source: str, expected: int = 201) -> dict:
        response = client.post(f"/v1/projects/{self.project_id}/rubrics", headers=self.headers, json={"yaml_source": yaml_source})
        assert response.status_code == expected, response.text
        return response.json()

    def evaluate(self, trace_id: str, rubric_id: str):
        return client.post(
            "/v1/evaluations/run",
            headers=self.headers,
            json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "test"},
        )


def rubric_yaml(evaluators: str, slug: str = "r", extra: str = "") -> str:
    return f"slug: {slug}\nname: R\ndescription: R\nthreshold: 0.7\n{extra}evaluators:\n{evaluators}"


GUARD = """  - id: sem_preco
    type: regex_match
    config: {target: trace.output.text, pattern: 'R\\$', mode: must_not_match}
"""
JUDGE = """  - id: juiz
    type: llm_judge
    config: {model: openai/gpt-4o-mini, prompt: "Avalie {{ trace.output.text }}", cost_cap_usd: 1%s}
"""
LENGTH = """  - id: tamanho
    type: length_bounds
    config: {target: trace.output.text, max: 500}
"""


def _judge_replies(monkeypatch, *replies) -> list:
    calls: list = []
    queue = list(replies)

    def fake(model, messages, temperature):
        calls.append(model)
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm_judge, "call_llm", fake)
    return calls


# ── Item 10: nothing to evaluate is not a pass ───────────────────────────────


def test_trace_without_answer_has_no_verdict() -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(GUARD + LENGTH))["rubric"]["id"]
    run = ws.evaluate(ws.ingest(answer=None), rubric_id).json()["run"]
    assert run["status"] == "error"
    assert run["passed"] is None
    assert run["aggregate_score"] is None
    assert run["error"] == {"code": "all_evaluators_failed", "reasons": ["empty_target"]}


def test_judge_is_not_called_without_answer(monkeypatch) -> None:
    calls = _judge_replies(monkeypatch, '{"score": 1}')
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(JUDGE % ""))["rubric"]["id"]
    run = ws.evaluate(ws.ingest(answer=None), rubric_id).json()["run"]
    assert (run["status"], calls) == ("error", [])


# ── Item 11: invalid rubrics do not save ─────────────────────────────────────


@pytest.mark.parametrize("evaluators", [
    "  - {id: e, type: regex_match, config: {target: trace.outptu.txet, pattern: x}}\n",
    "  - {id: e, type: regex_match, config: {target: trace.output.text}}\n",
    "  - {id: e, type: regex_match, config: {target: trace.output.text, pattern: '('}}\n",
    "  - {id: e, type: regex_match, config: {target: trace.output.text, pattern: x, mode: nope}}\n",
    "  - {id: e, type: keyword_presence, config: {target: trace.output.text, keywords: []}}\n",
    "  - {id: e, type: length_bounds, config: {target: trace.output.text}}\n",
    "  - {id: e, type: json_schema_valid, config: {target: trace.output.text, schema: {type: nope}}}\n",
    "  - {id: e, type: exact_match, config: {target: trace.output.text}}\n",
    "  - {id: e, type: cosine_similarity, config: {target_a: trace.output.text}}\n",
    "  - {id: e, type: llm_judge, config: {}}\n",
    "  - {id: e, type: llm_judge, config: {prompt: '{% if %}'}}\n",
    "  - {id: e, type: llm_judge, config: {prompt: x, repeats: 6}}\n",
])
def test_invalid_evaluator_config_is_rejected(evaluators) -> None:
    Workspace().rubric(rubric_yaml(evaluators), expected=422)


def test_length_limit_in_words_counts_words() -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml("  - {id: e, type: length_bounds, config: {target: trace.output.text, max_words: 3}}\n"))["rubric"]["id"]
    assert ws.evaluate(ws.ingest(answer="uma frase bem curta mesmo"), rubric_id).json()["run"]["passed"] is False
    assert ws.evaluate(ws.ingest(answer="duas palavras"), rubric_id).json()["run"]["passed"] is True


def test_fields_nothing_reads_are_reported() -> None:
    created = Workspace().rubric(rubric_yaml(LENGTH, extra="cost_limits: {max: 1}\nthresholds: {x: 1}\n"))
    assert created["ignored_fields"] == ["thresholds", "cost_limits"]


# ── Item 13: critical flags ──────────────────────────────────────────────────

FLAGS = """critical_flags:
  - {slug: inventou_preco, description: x, severity: critical, auto_fail: true}
"""


def test_flag_without_a_judge_is_rejected() -> None:
    Workspace().rubric(rubric_yaml(LENGTH, extra=FLAGS), expected=422)


def test_flag_raised_by_judge_fails_the_run(monkeypatch) -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(JUDGE % "", extra=FLAGS))["rubric"]["id"]
    _judge_replies(monkeypatch, '{"score": 0.95, "flags": ["inventou_preco"]}')
    run = ws.evaluate(ws.ingest(), rubric_id).json()["run"]
    assert run["passed"] is False
    assert run["run_metadata"]["raised_flags"] == ["inventou_preco"]


def test_flag_not_raised_does_not_fail_the_run(monkeypatch) -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(JUDGE % "", extra=FLAGS))["rubric"]["id"]
    _judge_replies(monkeypatch, '{"score": 0.95, "flags": []}')
    assert ws.evaluate(ws.ingest(), rubric_id).json()["run"]["passed"] is True


# ── Item 14: failures to measure are not quality ─────────────────────────────


def test_judge_down_leaves_score_of_the_rest_and_no_verdict(monkeypatch) -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(JUDGE % "" + LENGTH))["rubric"]["id"]
    _judge_replies(monkeypatch, httpx.ConnectTimeout("timeout"))
    trace_id = ws.ingest()
    run = ws.evaluate(trace_id, rubric_id).json()["run"]
    assert (run["status"], run["passed"], run["aggregate_score"]) == ("completed", None, 1.0)
    with SessionLocal() as db:
        # Persisted, not only in memory: the retry and the gate read it from the database.
        assert db.query(EvaluationRun).filter_by(trace_id=trace_id).one().run_metadata["partial_failure"] is True


def test_infra_failure_of_auto_fail_evaluator_is_not_an_auto_fail(monkeypatch) -> None:
    ws = Workspace()
    conditions = "automatic_fail_conditions:\n  - {slug: c, description: x, evaluator_id: juiz}\n"
    rubric_id = ws.rubric(rubric_yaml(JUDGE % "" + LENGTH, extra=conditions))["rubric"]["id"]
    _judge_replies(monkeypatch, httpx.ConnectTimeout("timeout"))
    run = ws.evaluate(ws.ingest(), rubric_id).json()["run"]
    assert run["passed"] is None
    assert "auto_failed" not in run["run_metadata"]


@pytest.mark.parametrize("reply", ['{"veredito":"ok"}', '{"score": 85}', '{"score": true}', '["score"]', "texto"])
def test_judge_reply_without_valid_score_is_an_error(monkeypatch, reply) -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(JUDGE % ""))["rubric"]["id"]
    _judge_replies(monkeypatch, reply)
    run = ws.evaluate(ws.ingest(), rubric_id).json()["run"]
    assert (run["status"], run["passed"]) == ("error", None)
    assert run["error"]["reasons"] == ["judge_invalid_response"]


# ── Item 15: evaluating again ────────────────────────────────────────────────


def test_failed_run_can_be_evaluated_again_keeping_its_cost(monkeypatch) -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(JUDGE % ""))["rubric"]["id"]
    trace_id = ws.ingest()
    _judge_replies(monkeypatch, "texto")
    first = ws.evaluate(trace_id, rubric_id).json()["run"]
    assert first["status"] == "error" and first["cost_usd"] > 0

    _judge_replies(monkeypatch, '{"score": 0.9}')
    second = ws.evaluate(trace_id, rubric_id)
    assert second.status_code == 201
    run = second.json()["run"]
    assert (run["status"], run["passed"], run["run_metadata"]["attempt"]) == ("completed", True, 2)
    assert run["cost_usd"] > first["cost_usd"]
    with SessionLocal() as db:
        assert db.query(EvaluationRun).filter_by(trace_id=trace_id).count() == 1

    third = ws.evaluate(trace_id, rubric_id)
    assert third.status_code == 409
    assert third.json()["detail"]["existing_run_id"] == run["id"]


def test_partial_run_can_be_evaluated_again(monkeypatch) -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(JUDGE % "" + LENGTH))["rubric"]["id"]
    trace_id = ws.ingest()
    _judge_replies(monkeypatch, httpx.ConnectTimeout("timeout"))
    ws.evaluate(trace_id, rubric_id)
    _judge_replies(monkeypatch, '{"score": 0.9}')
    assert ws.evaluate(trace_id, rubric_id).json()["run"]["passed"] is True


# ── Item 19: judge provider ──────────────────────────────────────────────────


@pytest.mark.parametrize("model,url,sent_model,env", [
    ("openrouter/openai/gpt-6-luna", "https://openrouter.ai/api/v1/chat/completions", "openai/gpt-6-luna", "OPENROUTER_API_KEY"),
    ("gemini/gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash", "GEMINI_API_KEY"),
    ("groq/llama-3.3-70b-versatile", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    ("openai/gpt-4o-mini", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini", "OPENAI_API_KEY"),
    ("gpt-4o-mini", "https://api.openai.com/v1/chat/completions", "gpt-4o-mini", "OPENAI_API_KEY"),
])
def test_judge_routes_by_provider_prefix(monkeypatch, model, url, sent_model, env) -> None:
    sent = {}

    def fake_post(target, **kwargs):
        sent.update(url=target, model=kwargs["json"]["model"], auth=kwargs["headers"]["Authorization"])
        request = httpx.Request("POST", target)
        return httpx.Response(200, request=request, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setenv(env, "chave-falsa")
    monkeypatch.setattr(httpx, "post", fake_post)
    assert llm_judge._call_llm(model, [], 0) == "ok"
    assert sent == {"url": url, "model": sent_model, "auth": "Bearer chave-falsa"}


def test_judge_without_key_or_with_unknown_provider_does_not_call_out(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: pytest.fail("no network expected"))
    with pytest.raises(ValueError, match="judge_key_not_configured:OPENROUTER_API_KEY"):
        llm_judge._call_llm("openrouter/x", [], 0)
    with pytest.raises(ValueError, match="unsupported_judge_provider:acme"):
        llm_judge._call_llm("acme/x", [], 0)


def test_unconfigured_judge_spends_nothing(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    ws = Workspace()
    judge = '  - {id: j, type: llm_judge, config: {model: openrouter/x/y, prompt: x, cost_cap_usd: 1}}\n'
    rubric_id = ws.rubric(rubric_yaml(judge + LENGTH))["rubric"]["id"]
    run = ws.evaluate(ws.ingest(), rubric_id).json()["run"]
    assert (run["passed"], run["cost_usd"]) == (None, 0)


# ── Item 20: judge budget ────────────────────────────────────────────────────


def test_every_judge_attempt_is_charged(monkeypatch) -> None:
    _judge_replies(monkeypatch, "texto", '{"score": 0.9}')
    two = llm_judge.run({}, {"model": "openai/gpt-4o-mini", "prompt": "x" * 400, "cost_cap_usd": 1})
    _judge_replies(monkeypatch, '{"score": 0.9}')
    one = llm_judge.run({}, {"model": "openai/gpt-4o-mini", "prompt": "x" * 400, "cost_cap_usd": 1})
    assert two.score == 0.9
    assert two.cost_usd > one.cost_usd


def test_judge_budget_counts_other_projects_of_the_org_and_experiments(monkeypatch) -> None:
    ws = Workspace()
    sibling = Workspace("org-a", org_id=ws.org_id)
    rubric_id = ws.rubric(rubric_yaml(JUDGE % ""))["rubric"]["id"]
    _judge_replies(monkeypatch, '{"score": 0.9}')
    run = ws.evaluate(ws.ingest(), rubric_id).json()["run"]
    with SessionLocal() as db:
        spent = eval_service._judge_spent_this_month(sibling.project_id, db)
        assert spent == pytest.approx(run["cost_usd"], abs=1e-6)
        from app.models import Dataset, Experiment, ExperimentRun

        dataset = Dataset(id=new_id("ds"), project_id=sibling.project_id, slug="d")
        db.add(dataset)
        db.flush()
        experiment = Experiment(
            id=new_id("exp"), project_id=sibling.project_id, name="e", dataset_id=dataset.id, rubric_id=rubric_id,
            variants=[], pass_criteria={},
        )
        db.add(experiment)
        db.flush()
        db.add(ExperimentRun(
            id=new_id("exr"), experiment_id=experiment.id, project_id=sibling.project_id,
            by_variant={"a": {"total_cost_usd": 0.5}, "b": {"total_cost_usd": 0.25}},
        ))
        db.commit()
        assert eval_service._judge_spent_this_month(ws.project_id, db) == pytest.approx(run["cost_usd"] + 0.75, abs=1e-6)


# ── Item 17: overview score ──────────────────────────────────────────────────


def test_overview_score_uses_runs_with_a_verdict(monkeypatch) -> None:
    ws = Workspace()
    rubric = ws.rubric(rubric_yaml(GUARD + LENGTH))["rubric"]["id"]
    ws.evaluate(ws.ingest(answer="sem nada"), rubric)
    ws.evaluate(ws.ingest(answer="custa R$ 1"), rubric)
    ws.evaluate(ws.ingest(answer=None), rubric)
    ws.ingest()
    kpis = client.get("/v1/analytics/overview", headers=ws.headers, params={"project_id": ws.project_id, "window": "24h"}).json()["kpis"]
    assert kpis["avg_score"] == pytest.approx(0.75)
    assert kpis["evaluated_traces"] == 2
    assert kpis["traces"] == 4


# ── Item 18: cost ────────────────────────────────────────────────────────────


def test_tokens_without_a_price_are_labeled_unpriced() -> None:
    ws = Workspace()
    now = datetime.now(timezone.utc).isoformat()
    span = {
        "client_span_id": "s", "type": "llm_call", "name": "l", "status": "ok", "started_at": now, "ended_at": now,
        "provider": "openrouter", "model": "openai/gpt-6-luna", "tokens_in": 1000, "tokens_out": 500,
    }
    trace = {"client_trace_id": "c", "name": "t", "environment": "dev", "status": "ok", "started_at": now, "ended_at": now, "spans": [span]}
    client.post("/v1/traces", headers={"X-EvalOps-Key": ws.key}, json={"traces": [trace]})
    item = client.get("/v1/traces", headers=ws.headers, params={"project_id": ws.project_id}).json()["data"][0]
    assert (item["total_cost_usd"], item["cost_source"]) == (0.0, "unpriced")


def test_price_table_matches_published_prices() -> None:
    assert float(compute_cost_usd("openai", "gpt-4.1", 1_000_000, 1_000_000)) == pytest.approx(10.0)
    assert float(compute_cost_usd("openai", "gpt-4o-mini", 1_000_000, 1_000_000)) == pytest.approx(0.75)
    assert float(compute_cost_usd("gemini", "gemini-2.5-flash", 1_000_000, 1_000_000)) == pytest.approx(2.8)
    assert float(compute_cost_usd("gemini", "gemini-2.5-pro", 1_000_000, 1_000_000)) == pytest.approx(11.25)


# ── Item 22: batch and key access ────────────────────────────────────────────


class _Pool:
    def __init__(self) -> None:
        self.jobs: list[dict] = []

    async def enqueue_job(self, name: str, **kwargs) -> None:
        self.jobs.append({"name": name, **kwargs})


def _use_pool() -> _Pool:
    pool = _Pool()
    app.dependency_overrides[get_arq_pool] = lambda: pool
    return pool


def test_batch_needs_the_evaluate_scope_and_a_key_of_that_project() -> None:
    ws, other = Workspace("org-a"), Workspace("org-b")
    _use_pool()
    rubric_id = ws.rubric(rubric_yaml(LENGTH))["rubric"]["id"]
    url = f"/v1/projects/{ws.project_id}/evaluations/batch"
    assert client.post(url, json={"rubric_id": rubric_id}).status_code == 401
    assert client.post(url, headers={"X-EvalOps-Key": ws.key}, json={"rubric_id": rubric_id}).status_code == 403
    other_key = other.create_key(["evaluate"])
    assert client.post(url, headers={"X-EvalOps-Key": other_key}, json={"rubric_id": rubric_id}).status_code == 404
    assert client.post(url, headers=other.headers, json={"rubric_id": rubric_id}).status_code == 404
    assert client.post(url, headers={"X-EvalOps-Key": ws.create_key(["evaluate"])}, json={"rubric_id": rubric_id}).status_code == 202


def test_key_scopes_are_validated_and_evaluate_is_not_default() -> None:
    ws = Workspace()
    url = f"/v1/projects/{ws.project_id}/api-keys"
    assert client.post(url, headers=ws.headers, json={"name": "xx", "environment": "dev", "scopes": ["admin"]}).status_code == 422
    assert client.post(url, headers=ws.headers, json={"name": "xx", "environment": "dev"}).json()["scopes"] == ["ingest", "read"]


def test_batch_queues_only_what_lacks_a_complete_run_and_respects_filters() -> None:
    ws = Workspace()
    pool = _use_pool()
    rubric_id = ws.rubric(rubric_yaml(LENGTH))["rubric"]["id"]
    done = ws.ingest(metadata={"batch": "b1"})
    ws.evaluate(done, rubric_id)
    failed = ws.ingest(answer=None, metadata={"batch": "b1"})
    ws.evaluate(failed, rubric_id)
    pending = ws.ingest(metadata={"batch": "b1"})
    outside = ws.ingest(metadata={"batch": "b2"})

    response = client.post(
        f"/v1/projects/{ws.project_id}/evaluations/batch",
        headers={"X-EvalOps-Key": ws.create_key(["evaluate"])},
        json={"rubric_id": rubric_id, "batch": "b1"},
    )
    assert response.status_code == 202
    assert set(response.json()["trace_ids"]) == {failed, pending}
    assert {job["trace_id"] for job in pool.jobs} == {failed, pending}
    assert outside not in response.json()["trace_ids"]
    assert all(job["name"] == "evaluate_trace_job" and job["rubric_version"] == 1 for job in pool.jobs)


def test_worker_evaluates_and_skips_what_is_done() -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(LENGTH))["rubric"]["id"]
    trace_id = ws.ingest()
    assert _evaluate(SessionLocal, trace_id, rubric_id, 1, "batch")["status"] == "completed"
    assert _evaluate(SessionLocal, trace_id, rubric_id, 1, "batch") == {"status": "skipped", "reason": "already_evaluated"}
    assert _evaluate(SessionLocal, "tr_nao_existe", rubric_id, 1, "batch") == {"status": "skipped", "reason": "not_found"}


# ── Item 23: conversation and trend ──────────────────────────────────────────


def test_rubric_reads_the_conversation_up_to_the_evaluated_turn(monkeypatch) -> None:
    ws = Workspace()
    prompts = []

    def fake(model, messages, temperature):
        prompts.append(messages[0]["content"])
        return '{"score": 0.9}'

    monkeypatch.setattr(llm_judge, "call_llm", fake)
    rubric_id = ws.rubric(rubric_yaml(
        '  - {id: j, type: llm_judge, config: {prompt: "{{ trace.conversation.transcript }}", cost_cap_usd: 1}}\n'
    ))["rubric"]["id"]
    meta = {"metadata": {"conversation_id": "c1"}}
    ws.ingest(user="quero alugar", answer="em qual bairro?", offset_s=0, **meta)
    second = ws.ingest(user="Copacabana", answer="achei três", offset_s=10, **meta)
    ws.ingest(user="depois", answer="não deve entrar", offset_s=20, **meta)
    ws.ingest(user="outra conversa", answer="fora", offset_s=5, metadata={"conversation_id": "c2"})

    assert ws.evaluate(second, rubric_id).status_code == 201
    assert prompts == ["user: quero alugar\nassistant: em qual bairro?\nuser: Copacabana\nassistant: achei três"]
    listed = client.get("/v1/traces", headers=ws.headers, params={"project_id": ws.project_id, "conversation_id": "c1"}).json()
    assert len(listed["data"]) == 3


def test_judge_repeats_report_the_spread(monkeypatch) -> None:
    calls = _judge_replies(monkeypatch, '{"score": 0.8, "flags": ["a"]}', '{"score": 0.6, "flags": ["b"]}')
    result = llm_judge.run({}, {"prompt": "x", "repeats": 2, "cost_cap_usd": 1, "pass_threshold": 0.65})
    assert len(calls) == 2
    assert result.score == pytest.approx(0.7)
    assert result.passed is True
    assert result.raw_output["samples"] == [0.8, 0.6]
    assert result.raw_output["stddev"] == pytest.approx(0.1)
    assert result.raw_output["flags"] == ["a", "b"]


def test_report_compares_versions_and_is_readable_with_a_key() -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(GUARD))["rubric"]["id"]
    ws.evaluate(ws.ingest(answer="sem nada", metadata={"batch": "b1"}), rubric_id)
    ws.evaluate(ws.ingest(answer="custa R$ 1", metadata={"batch": "b1"}), rubric_id)
    ws.evaluate(ws.ingest(answer=None, metadata={"batch": "b1"}), rubric_id)
    ws.ingest(metadata={"batch": "b1"})
    ws.evaluate(ws.ingest(answer="fora", metadata={"batch": "b2"}), rubric_id)
    url = f"/v1/projects/{ws.project_id}/rubrics/{rubric_id}/report"

    response = client.get(url, headers={"X-EvalOps-Key": ws.key}, params={"batch": "b1"})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["trace_count"] == 4
    totals = report["totals"]
    assert (totals["runs"], totals["passed"], totals["failed"], totals["errors"], totals["unknown"]) == (3, 1, 1, 1, 0)
    assert totals["pass_rate"] == 0.5
    assert totals["avg_score"] == 0.5
    assert totals["score_stddev"] == 0.5
    assert [row["rubric_version"] for row in report["by_version"]] == [1]
    assert report["by_day"][0]["runs"] == 3
    assert report["by_evaluator"][0]["errors"] == 1
    assert report["by_evaluator"][0]["pass_rate"] == 0.5

    client.post(f"/v1/rubrics/{rubric_id}/versions", headers=ws.headers, json={"yaml_source": rubric_yaml(LENGTH)})
    ws.evaluate(ws.ingest(answer="nova", metadata={"batch": "b1"}), rubric_id)
    report = client.get(url, headers=ws.headers, params={"batch": "b1"}).json()
    assert [row["rubric_version"] for row in report["by_version"]] == [1, 2]

    assert client.get(url, headers=ws.headers, params={"window": "1y"}).status_code == 422
    other = Workspace("org-b")
    assert client.get(url, headers=other.headers).status_code == 404
    assert client.get(url, headers={"X-EvalOps-Key": other.key}).status_code == 404


# ── Item 24: notifications and causes ────────────────────────────────────────


def test_problems_notify_once_per_hour_and_good_runs_do_not() -> None:
    ws = Workspace()
    rubric_id = ws.rubric(rubric_yaml(LENGTH))["rubric"]["id"]
    ws.evaluate(ws.ingest(), rubric_id)
    with SessionLocal() as db:
        assert db.query(Notification).count() == 0
    ws.evaluate(ws.ingest(answer=None), rubric_id)
    ws.evaluate(ws.ingest(answer=None), rubric_id)
    listed = client.get(f"/v1/projects/{ws.project_id}/notifications", headers=ws.headers).json()
    assert [(row["kind"], row["title"]) for row in listed["data"]] == [("err", "Avaliação com erro: r")]
    assert listed["unread_count"] == 1


def test_attention_does_not_invent_causes() -> None:
    ws = Workspace()
    now = datetime.now(timezone.utc).isoformat()
    span = {
        "client_span_id": "s", "type": "retrieval", "name": "r", "status": "error", "started_at": now, "ended_at": now,
        "error": {"message": "vector store timeout"},
    }
    base = {"environment": "dev", "started_at": now, "ended_at": now}
    client.post("/v1/traces", headers={"X-EvalOps-Key": ws.key}, json={"traces": [
        {"client_trace_id": "a", "name": "a", "status": "error", "spans": [span], **base},
        {"client_trace_id": "b", "name": "b", "status": "partial", "spans": [], **base},
    ]})
    items = client.get(f"/v1/projects/{ws.project_id}/attention", headers=ws.headers).json()["items"]
    assert sorted(item["cause"] for item in items) == ["partial_trace", "timeout"]
