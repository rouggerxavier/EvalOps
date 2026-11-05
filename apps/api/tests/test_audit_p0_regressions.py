"""Regressions for the P0 findings in docs/audits/auditoria-codigo-2026-11-05.md."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.domain.evaluators import exact_match, llm_judge
from app.domain.rubrics.resolver import build_trace_context
from app.domain.services import usage_service
from app.domain.services.experiment_service import _render_template
from app.main import app
from app.models import Membership, Organization, Plan, Project, Span, Subscription, Trace, User
from app.security import create_access_token, new_id
from app.workers.replay_worker import _render

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT.parents[1] / "packages" / "sdk-python"))

from evalops.tracer import EvalOpsTracer  # noqa: E402

client = TestClient(app)

READ_ENV = "{{ cycler.__init__.__globals__.os.environ['JWT_SECRET'] }}"
RUN_COMMAND = "{{ cycler.__init__.__globals__.os.popen('echo pwned').read() }}"


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _bootstrap(slug: str = "org-a") -> tuple[dict, str, str]:
    """Returns (auth headers, org id, project id)."""
    user_id, org_id, project_id = new_id("usr"), new_id("org"), new_id("prj")
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{slug}@example.com", name="Audit"))
        db.add(Organization(id=org_id, name=slug, slug=slug))
        db.flush()
        db.add(Membership(user_id=user_id, organization_id=org_id, role="owner"))
        db.add(Project(id=project_id, organization_id=org_id, name=slug, slug=slug))
        db.commit()
    token = create_access_token(sub=user_id, email=f"{slug}@example.com", name="Audit")
    return {"Authorization": f"Bearer {token}"}, org_id, project_id


# ── Template injection ───────────────────────────────────────────────────────


@pytest.mark.parametrize("template", [READ_ENV, RUN_COMMAND])
def test_exact_match_template_cannot_reach_the_server(template) -> None:
    result = exact_match.run({"trace": {"output": {"text": "x"}}}, {"target": "trace.output.text", "expected": template})
    assert result.raw_output["expected"] == template


def test_judge_prompt_template_cannot_reach_the_server(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "segredo-de-teste")
    assert "segredo-de-teste" not in llm_judge._render_prompt(READ_ENV, {})


def test_experiment_template_cannot_reach_the_server(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "segredo-de-teste")
    assert "segredo-de-teste" not in _render_template(READ_ENV, {})


def test_legitimate_templates_still_render() -> None:
    assert llm_judge._render_prompt("Avalie: {{ trace.output.text }}", {"trace": {"output": {"text": "oi"}}}) == "Avalie: oi"
    assert _render_template("Olá {{ user_message }}", {"user_message": "Ana"}) == "Olá Ana"


def test_replay_never_evaluates_message_content() -> None:
    assert _render(RUN_COMMAND, {"x": 1}) == RUN_COMMAND
    assert _render("{{ 7 * 7 }} {{nome}} {{outro}}", {"nome": "{{ 7 * 7 }}"}) == "{{ 7 * 7 }} {{ 7 * 7 }} {{outro}}"


# ── Deployment ───────────────────────────────────────────────────────────────


def test_revision_ids_fit_alembic_version_column() -> None:
    config = Config()
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    revisions = [script.revision for script in ScriptDirectory.from_config(config).walk_revisions()]
    assert revisions
    assert [revision for revision in revisions if len(revision) > 32] == []


# ── Output the evaluators read ───────────────────────────────────────────────


def _span(trace_id: str, **fields) -> Span:
    now = datetime.now(timezone.utc)
    defaults = dict(id=new_id("sp"), trace_id=trace_id, type="llm_call", name="llm", status="ok",
                    started_at=now, ended_at=now, duration_ms=0, metadata_json={})
    return Span(**{**defaults, **fields})


def _output(spans: list[Span], metadata: dict | None = None) -> str:
    trace = Trace(id="tr", name="t", status="ok", tags={}, metadata_json=metadata or {})
    return build_trace_context(trace, spans)["trace"]["output"]["text"]


def test_output_skips_last_call_that_only_has_tool_calls() -> None:
    assert _output([
        _span("tr", messages_out=[{"role": "assistant", "content": "resposta"}]),
        _span("tr", messages_out=[{"role": "assistant", "content": None, "tool_calls": [{"name": "busca"}]}]),
    ]) == "resposta"


def test_output_prefers_messages_then_metadata_then_span_output() -> None:
    both = _span("tr", messages_out=[{"role": "assistant", "content": "mensagem"}], output={"text": "campo"})
    assert _output([both], {"output": "metadata"}) == "mensagem"
    assert _output([_span("tr", output={"text": "campo"})], {"output": "metadata"}) == "metadata"
    assert _output([_span("tr", output={"text": "campo"})]) == "campo"


def test_output_falls_back_to_root_result_without_llm_span() -> None:
    root = _span("tr", type="chain", parent_span_id=None, output={"result": "retorno"})
    assert _output([root]) == "retorno"


# ── SDK → API → evaluation ───────────────────────────────────────────────────


class _Capture:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def submit(self, payload: dict) -> None:
        self.items.append(payload)


def _sdk_payload(record_call) -> dict:
    tracer = EvalOpsTracer()
    tracer.init(api_key="x", project="p", environment="dev", disabled=True)
    tracer._disabled = False
    tracer._uploader = _Capture()

    @tracer.trace("agente.turno")
    def turn() -> str:
        with tracer.span("llm.generate", type="llm_call") as span:
            record_call(span)
        return "fim"

    turn()
    return tracer._uploader.items[0]


GUARD = """
slug: guarda-preco
name: Guarda
description: nao inventa preco
threshold: 0.7
evaluators:
  - id: sem_preco
    type: regex_match
    config: {target: trace.output.text, pattern: 'R\\$', mode: must_not_match}
"""


def _ingest_and_evaluate(headers: dict, project_id: str, payload: dict) -> tuple[dict, dict]:
    key = client.post(f"/v1/projects/{project_id}/api-keys", headers=headers, json={"name": "sdk", "environment": "dev"}).json()["key"]
    ingested = client.post("/v1/traces", headers={"X-EvalOps-Key": key}, json={"traces": [payload]})
    assert ingested.status_code == 202, ingested.text
    assert ingested.json()["errors"] == []
    trace_id = ingested.json()["results"][0]["trace_id"]
    rubric = client.post(f"/v1/projects/{project_id}/rubrics", headers=headers, json={"yaml_source": GUARD})
    run = client.post("/v1/evaluations/run", headers=headers, json={
        "trace_id": trace_id, "rubric_id": rubric.json()["rubric"]["id"], "triggered_by": "manual",
    })
    assert run.status_code == 201, run.text
    trace = client.get(f"/v1/traces/{trace_id}", headers=headers).json()
    return run.json()["run"], trace


@pytest.mark.parametrize("record", [
    lambda span: span.set_llm(messages_out=[{"role": "assistant", "content": "Custa R$ 999.999"}]),
    lambda span: span.set_io(output={"text": "Custa R$ 999.999"}),
])
def test_bad_answer_sent_by_the_sdk_fails_the_rubric(record) -> None:
    headers, _, project_id = _bootstrap()
    run, _ = _ingest_and_evaluate(headers, project_id, _sdk_payload(record))
    assert run["status"] == "completed"
    assert run["passed"] is False


def test_good_answer_sent_by_the_sdk_passes_the_rubric() -> None:
    headers, _, project_id = _bootstrap()
    payload = _sdk_payload(lambda span: span.set_llm(messages_out=[{"role": "assistant", "content": "Posso ajudar?"}]))
    run, _ = _ingest_and_evaluate(headers, project_id, payload)
    assert run["passed"] is True


def test_sdk_model_tokens_and_cost_reach_the_trace() -> None:
    headers, _, project_id = _bootstrap()
    payload = _sdk_payload(lambda span: span.set_llm(
        provider="openrouter", model="openai/gpt-6-luna", tokens_in=1000, tokens_out=500, cost_usd=0.0123,
        messages_in=[{"role": "user", "content": "oi"}], messages_out=[{"role": "assistant", "content": "olá"}],
    ))
    _, detail = _ingest_and_evaluate(headers, project_id, payload)
    span = next(s for s in detail["spans"] if s["type"] == "llm_call")
    assert (span["provider"], span["model"], span["tokens_in"], span["tokens_out"]) == ("openrouter", "openai/gpt-6-luna", 1000, 500)
    assert span["cost_usd"] == pytest.approx(0.0123)
    assert detail["trace"]["total_cost_usd"] == pytest.approx(0.0123)
    assert detail["trace"]["cost_source"] == "provided"


# ── Organization limits ──────────────────────────────────────────────────────


def test_org_limits_change_only_that_org() -> None:
    _, org_a, project_a = _bootstrap("org-a")
    _, org_b, project_b = _bootstrap("org-b")
    with SessionLocal() as db:
        usage_service.ensure_subscription(db, org_b)
        usage_service.set_org_plan_limits(db, org_a, monthly_trace_limit=5000)
        usage_service.set_org_plan_limits(db, org_a, monthly_eval_limit=700)
        db.commit()
    with SessionLocal() as db:
        plan_a = db.get(Plan, db.query(Subscription).filter_by(organization_id=org_a).one().plan_id)
        plan_b = db.get(Plan, db.query(Subscription).filter_by(organization_id=org_b).one().plan_id)
        assert (plan_a.monthly_trace_limit, plan_a.monthly_eval_limit) == (5000, 700)
        assert plan_a.monthly_span_limit == 50_000
        assert (plan_b.code, plan_b.monthly_trace_limit) == ("free", 1000)
        usage_service.enforce_quota(db, db.get(Project, project_a), "traces_ingested", 5000)
        with pytest.raises(Exception) as denied:
            usage_service.enforce_quota(db, db.get(Project, project_b), "traces_ingested", 5000)
        assert denied.value.status_code == 402


def test_limits_script_rejects_invalid_values() -> None:
    for args in (["--org", "x"], ["--org", "x", "--traces", "0"], ["--org", "x", "--tokens", str(2**31)], ["--org", "x", "--judge-budget-usd", "inf"]):
        done = subprocess.run([sys.executable, "scripts/set_org_limits.py", *args], cwd=API_ROOT, capture_output=True, text=True)
        assert done.returncode == 2, (args, done.stdout, done.stderr)
