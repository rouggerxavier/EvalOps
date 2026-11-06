"""Regressions for docs/audits/auditoria-produto-2026-11-05.md: what the dashboard reads from the API."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.domain.rubrics.parser import parse_rubric_yaml
from app.main import app
from app.models import EvaluationRun, User
from app.security import create_access_token, new_id

client = TestClient(app)
WEB = Path(__file__).resolve().parents[2] / "web"
LENGTH = "  - {id: tamanho, type: length_bounds, config: {target: trace.output.text, max: 500}}\n"


@pytest.fixture()
def ws():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    user_id = new_id("usr")
    with SessionLocal() as db:
        db.add(User(id=user_id, email="p@example.com", name="P"))
        db.commit()
    headers = {"Authorization": "Bearer " + create_access_token(sub=user_id, email="p@example.com", name="P")}
    org = client.post("/v1/organizations", headers=headers, json={"name": "Org", "slug": "org-p"}).json()
    project = client.post(
        "/v1/projects", headers=headers, json={"organization_id": org["id"], "name": "Prj", "slug": "prj-p"}
    ).json()
    key = client.post(
        f"/v1/projects/{project['id']}/api-keys",
        headers=headers,
        json={"name": "chave", "environment": "dev", "scopes": ["ingest", "read"]},
    ).json()["key"]
    yield {"headers": headers, "project": project["id"], "key": key}
    Base.metadata.drop_all(bind=engine)


def ingest(ws, name="t", environment="dev", spans=None, **extra) -> str:
    now = datetime.now(timezone.utc)
    default = [{
        "client_span_id": "s", "type": "llm_call", "name": "l", "status": "ok",
        "started_at": now.isoformat(), "ended_at": now.isoformat(),
        "model": "gpt-4o-mini", "messages_out": [{"role": "assistant", "content": "ola"}],
    }]
    trace = {
        "client_trace_id": new_id("ct"), "name": name, "environment": environment, "status": "ok",
        "started_at": now.isoformat(), "ended_at": (now + timedelta(seconds=5)).isoformat(),
        "spans": default if spans is None else spans,
        **extra,
    }
    response = client.post("/v1/traces", headers={"X-EvalOps-Key": ws["key"]}, json={"traces": [trace]})
    assert response.status_code == 202 and response.json()["errors"] == [], response.text
    return response.json()["results"][0]["trace_id"]


def rubric(ws, slug="r") -> str:
    yaml_source = f"slug: {slug}\nname: R\ndescription: R\nthreshold: 0.5\nevaluators:\n{LENGTH}"
    response = client.post(f"/v1/projects/{ws['project']}/rubrics", headers=ws["headers"], json={"yaml_source": yaml_source})
    assert response.status_code == 201, response.text
    return response.json()["rubric"]["id"]


def _span(client_id: str, offset_s: int, model: str | None, type_: str = "llm_call") -> dict:
    at = (datetime.now(timezone.utc) + timedelta(seconds=offset_s)).isoformat()
    return {
        "client_span_id": client_id, "type": type_, "name": client_id, "status": "ok",
        "started_at": at, "ended_at": at, "model": model,
    }


def test_trace_model_is_the_newest_llm_call(ws) -> None:
    trace_id = ingest(ws, spans=[_span("late", 3, "modelo-final"), _span("early", 1, "modelo-inicial"), _span("tool", 4, None, "tool")])
    item = client.get("/v1/traces", headers=ws["headers"], params={"project_id": ws["project"]}).json()["data"][0]
    assert item["model"] == "modelo-final"
    detail = client.get(f"/v1/traces/{trace_id}", headers=ws["headers"]).json()
    assert detail["trace"]["model"] == "modelo-final"
    assert [span["name"] for span in detail["spans"]] == ["early", "late", "tool"]


def test_flags_are_readable_and_filterable(ws) -> None:
    flagged, other = ingest(ws, "marcado"), ingest(ws, "limpo")
    response = client.post(f"/v1/traces/{flagged}/flags", headers=ws["headers"], json={"reason": "manual", "note": "ver"})
    assert response.status_code < 300, response.text

    detail = client.get(f"/v1/traces/{flagged}", headers=ws["headers"]).json()
    assert [(flag["reason"], flag["note"]) for flag in detail["flags"]] == [("manual", "ver")]
    assert client.get(f"/v1/traces/{other}", headers=ws["headers"]).json()["flags"] == []

    params = {"project_id": ws["project"]}
    rows = client.get("/v1/traces", headers=ws["headers"], params=params).json()["data"]
    assert {row["name"]: row["flag_count"] for row in rows} == {"marcado": 1, "limpo": 0}
    only = client.get("/v1/traces", headers=ws["headers"], params={**params, "flagged": True}).json()["data"]
    assert [row["id"] for row in only] == [flagged]


def test_trace_list_filters_by_period_tag_user_model_score_and_search(ws) -> None:
    alvo = ingest(
        ws, "atendimento", spans=[_span("l", 0, "modelo-a")],
        tags={"canal": "whatsapp"}, user_ref="cliente-1", metadata={"conversation_id": "conv-9"},
    )
    outro = ingest(ws, "outro", spans=[_span("l", 0, "modelo-b")], tags={"canal": "site"}, user_ref="cliente-2")
    rubric_id = rubric(ws)
    with SessionLocal() as db:
        for run_id, trace_id, passed, score in (("run-a", alvo, False, 0.2), ("run-b", outro, True, 0.9)):
            db.add(EvaluationRun(
                id=run_id, project_id=ws["project"], trace_id=trace_id, rubric_id=rubric_id, rubric_version=1,
                triggered_by="t", status="completed", aggregate_score=score, passed=passed,
            ))
        db.commit()

    def ids(**params):
        response = client.get("/v1/traces", headers=ws["headers"], params={"project_id": ws["project"], **params})
        assert response.status_code == 200, response.text
        return {row["id"] for row in response.json()["data"]}

    now = datetime.now(timezone.utc)
    assert ids(since=(now - timedelta(hours=1)).isoformat()) == {alvo, outro}
    assert ids(since=(now + timedelta(hours=1)).isoformat()) == set()
    assert ids(until=(now - timedelta(hours=1)).isoformat()) == set()
    assert ids(tag="canal:whatsapp") == {alvo}
    assert ids(user_ref="cliente-2") == {outro}
    assert ids(model="modelo-a") == {alvo}
    assert ids(failed=True) == {alvo}
    assert ids(score_lt=0.5) == {alvo}
    assert ids(q="atend") == ids(q=alvo) == ids(q="cliente-1") == ids(q="conv-9") == {alvo}

    for bad in ({"tag": "semdoispontos"}, {"since": "ontem"}, {"until": "2026-13-40"}, {"score_lt": "x"}):
        response = client.get("/v1/traces", headers=ws["headers"], params={"project_id": ws["project"], **bad})
        assert response.status_code == 422, bad


def test_evaluations_follow_the_environment(ws) -> None:
    rubric_id = rubric(ws)
    for environment in ("dev", "prod"):
        trace_id = ingest(ws, environment=environment)
        response = client.post(
            "/v1/evaluations/run", headers=ws["headers"], json={"trace_id": trace_id, "rubric_id": rubric_id, "triggered_by": "t"}
        )
        assert response.status_code == 201, response.text
    base = f"/v1/projects/{ws['project']}/evaluations"
    assert len(client.get(base, headers=ws["headers"]).json()["data"]) == 2
    assert len(client.get(base, headers=ws["headers"], params={"environment": "prod"}).json()["data"]) == 1
    summary = client.get(f"{base}/summary", headers=ws["headers"], params={"environment": "prod"}).json()
    assert summary["runs_7d"] == 1
    assert client.get(base, headers=ws["headers"], params={"environment": "nope"}).status_code == 422


@pytest.mark.parametrize("yaml_source,expected", [
    ("slug: r\nname: R\ndescription: d\nevaluators:\n  - {id: e, type: builtin}\n", "evaluators.0.type: unknown evaluator type 'builtin'"),
    ("slug: r\nevaluators: []\n", "name: Field required"),
    ("slug: r\nname: R\ndescription: d\nevaluators:\n  - {id: e, type: regex_match, config: {target: trace.outptu.txet, pattern: x}}\n", "regex_match.target must be a known path"),
    ("slug: [\n", "YAML parse error"),
])
def test_invalid_rubric_says_what_to_fix(ws, yaml_source, expected) -> None:
    response = client.post(f"/v1/projects/{ws['project']}/rubrics", headers=ws["headers"], json={"yaml_source": yaml_source})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail.startswith("invalid_rubric: ") and expected in detail
    assert len(detail) <= 216 and "\n" not in detail and "errors.pydantic.dev" not in detail


def test_rubric_form_defaults_are_accepted() -> None:
    project = WEB / "app" / "o" / "[org]" / "p" / "[project]"
    modal = (project / "evaluations" / "evaluations-modals.tsx").read_text(encoding="utf-8")
    page = (project / "rubrics" / "page.tsx").read_text(encoding="utf-8")
    defaults = re.findall(r"`(slug: [^`]+)`", modal + page)
    assert len(defaults) == 2
    for source in defaults:
        assert parse_rubric_yaml(source.replace("\\n", "\n")).evaluators
