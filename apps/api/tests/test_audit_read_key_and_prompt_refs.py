"""Items 16 and 17 of docs/audits/auditoria-produto-2026-11-05.md: read keys read, and ingest checks prompt refs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import create_access_token, new_id

client = TestClient(app)
RUBRIC = (
    "slug: r\nname: R\ndescription: R\nthreshold: 0.5\nevaluators:\n"
    "  - {id: tamanho, type: length_bounds, config: {target: trace.output.text, max: 500}}\n"
)


def _workspace(slug: str) -> dict:
    user_id = new_id("usr")
    with SessionLocal() as db:
        db.add(User(id=user_id, email=f"{slug}@example.com", name=slug))
        db.commit()
    headers = {"Authorization": "Bearer " + create_access_token(sub=user_id, email=f"{slug}@example.com", name=slug)}
    org = client.post("/v1/organizations", headers=headers, json={"name": slug, "slug": f"org-{slug}"}).json()
    project = client.post(
        "/v1/projects", headers=headers, json={"organization_id": org["id"], "name": slug, "slug": f"prj-{slug}"}
    ).json()

    def key(*scopes: str) -> dict:
        created = client.post(
            f"/v1/projects/{project['id']}/api-keys",
            headers=headers,
            json={"name": "-".join(scopes), "environment": "dev", "scopes": list(scopes)},
        )
        assert created.status_code == 201, created.text
        return {"X-EvalOps-Key": created.json()["key"]}

    return {"headers": headers, "project": project["id"], "key": key}


def _trace(prompt_ref: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "client_trace_id": new_id("ct"), "name": "t", "environment": "dev", "status": "ok",
        "started_at": now.isoformat(), "ended_at": (now + timedelta(seconds=1)).isoformat(),
        "spans": [{
            "client_span_id": "s", "type": "llm_call", "name": "l", "status": "ok",
            "started_at": now.isoformat(), "ended_at": now.isoformat(), "prompt_version_ref": prompt_ref,
            "messages_out": [{"role": "assistant", "content": "ola"}],
        }],
    }


@pytest.fixture()
def ws():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    ws = _workspace("alfa")
    ws["ingest"] = ws["key"]("ingest")
    ws["read"] = ws["key"]("read")
    headers, project = ws["headers"], ws["project"]
    ws["prompt"] = client.post(
        f"/v1/projects/{project}/prompts", headers=headers, json={"slug": "suporte", "template": "oi"}
    ).json()["prompt"]["id"]
    ws["rubric"] = client.post(
        f"/v1/projects/{project}/rubrics", headers=headers, json={"yaml_source": RUBRIC}
    ).json()["rubric"]["id"]
    ingested = client.post("/v1/traces", headers=ws["ingest"], json={"traces": [_trace()]}).json()
    ws["trace"] = ingested["results"][0]["trace_id"]
    ws["run"] = client.post(
        "/v1/evaluations/run", headers=headers, json={"trace_id": ws["trace"], "rubric_id": ws["rubric"], "triggered_by": "t"}
    ).json()["run"]["id"]
    client.post(f"/v1/traces/{ws['trace']}/feedback", headers=headers, json={"thumbs": "up"})
    yield ws
    Base.metadata.drop_all(bind=engine)


READS = [
    "/v1/traces?project_id={project}",
    "/v1/traces/{trace}",
    "/v1/projects/{project}/prompts",
    "/v1/prompts/{prompt}",
    "/v1/prompts/{prompt}/versions",
    "/v1/prompts/{prompt}/usage",
    "/v1/projects/{project}/rubrics",
    "/v1/rubrics/{rubric}",
    "/v1/rubrics/{rubric}/versions",
    "/v1/rubrics/{rubric}/versions/1",
    "/v1/projects/{project}/rubrics/{rubric}/report",
    "/v1/evaluations/{run}",
    "/v1/projects/{project}/evaluations",
    "/v1/projects/{project}/evaluations/summary",
    "/v1/projects/{project}/coverage",
    "/v1/traces/{trace}/evaluations",
    "/v1/traces/{trace}/feedback",
]


@pytest.mark.parametrize("path", READS)
def test_read_key_reads_and_other_keys_do_not(ws, path) -> None:
    url = path.format(**ws)
    assert client.get(url, headers=ws["headers"]).status_code == 200
    assert client.get(url, headers=ws["read"]).status_code == 200
    assert client.get(url, headers=ws["ingest"]).status_code == 403
    other = _workspace("beta")["key"]("read", "ingest")
    assert client.get(url, headers=other).status_code == 404


def test_read_key_does_not_write(ws) -> None:
    project, trace, read = ws["project"], ws["trace"], ws["read"]
    assert client.post("/v1/traces", headers=read, json={"traces": [_trace()]}).status_code == 403
    assert client.post(f"/v1/projects/{project}/evaluations/batch", headers=read, json={"rubric_id": ws["rubric"]}).status_code == 403
    assert client.post(f"/v1/projects/{project}/prompts", headers=read, json={"slug": "x", "template": "y"}).status_code == 401
    assert client.post(f"/v1/projects/{project}/rubrics", headers=read, json={"yaml_source": RUBRIC}).status_code == 401
    assert client.post(f"/v1/traces/{trace}/feedback", headers=read, json={"thumbs": "down"}).status_code == 403
    assert client.post(
        "/v1/evaluations/run", headers=read, json={"trace_id": trace, "rubric_id": ws["rubric"], "triggered_by": "t"}
    ).status_code == 401


def test_unknown_prompt_ref_is_a_per_trace_error(ws) -> None:
    other = _workspace("beta")
    client.post(f"/v1/projects/{other['project']}/prompts", headers=other["headers"], json={"slug": "alheio", "template": "x"})
    valid = ["suporte", "suporte@1", ws["prompt"]]
    invalid = ["fantasma@1", "suporte@9", "alheio"]
    traces = [_trace(ref) for ref in valid + invalid]
    response = client.post("/v1/traces", headers=ws["ingest"], json={"traces": traces})
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["ingested"] == len(valid)
    assert [e["index"] for e in body["errors"]] == [3, 4, 5]
    assert body["errors"][0] == {
        "index": 3, "client_trace_id": traces[3]["client_trace_id"], "message": "unknown prompt_version_ref: fantasma@1",
    }
    usage = client.get(f"/v1/prompts/{ws['prompt']}/usage", headers=ws["read"]).json()
    assert usage["usage_count"] == len(valid)
