"""Feedback authorization and the SDK boundary for audit items 18/19."""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, HumanFeedback, Trace, User
from app.security import create_access_token, new_id

client = TestClient(app)


@pytest.fixture()
def workspace():
    user_id = new_id("usr")
    with SessionLocal() as db:
        db.add(User(id=user_id, email="sdk@example.com", name="SDK"))
        db.commit()
    jwt = {"Authorization": "Bearer " + create_access_token(sub=user_id, email="sdk@example.com", name="SDK")}
    org = client.post("/v1/organizations", headers=jwt, json={"name": "SDK", "slug": "sdk"}).json()["id"]

    def project(slug):
        pid = client.post("/v1/projects", headers=jwt, json={
            "organization_id": org, "name": slug, "slug": slug,
        }).json()["id"]
        keys = {}
        for scope in ("ingest", "read", "evaluate"):
            response = client.post(f"/v1/projects/{pid}/api-keys", headers=jwt, json={
                "name": scope, "environment": "dev", "scopes": [scope],
            })
            assert response.status_code == 201, response.text
            keys[scope] = {"X-EvalOps-Key": response.json()["key"]}
        return pid, keys

    pid, keys = project("primary")
    now = datetime.now(timezone.utc).isoformat()

    def ingest(headers, cid="ct_shared"):
        result = client.post("/v1/traces", headers=headers, json={"traces": [{
            "client_trace_id": cid, "name": "sdk", "environment": "dev", "status": "ok",
            "started_at": now, "ended_at": now, "spans": [],
        }]})
        assert result.status_code == 202, result.text
        return result.json()["results"][0]["trace_id"]

    tid = ingest(keys["ingest"])
    return {"jwt": jwt, "user": user_id, "org": org, "pid": pid, "keys": keys,
            "tid": tid, "project": project, "ingest": ingest}


@pytest.mark.parametrize("by_client_id", [False, True])
def test_feedback_ingest_key_is_scoped_audited_and_read_cannot_write(workspace, by_client_id):
    ws = workspace
    path = f"/v1/traces/{'by-client-id/ct_shared' if by_client_id else ws['tid']}/feedback"
    other_pid, other_keys = ws["project"]("secondary")
    for headers, code in [({}, 401), (ws["keys"]["read"], 403), (ws["keys"]["evaluate"], 403),
                          (other_keys["ingest"], 404)]:
        assert client.post(path, headers=headers, json={"thumbs": "up"}).status_code == code
    other_tid = ws["ingest"](other_keys["ingest"])
    created = client.post(path, headers=ws["keys"]["ingest"], json={"thumbs": "up", "source": "sdk"})
    assert created.status_code == 201, created.text
    assert created.json()["feedback"]["trace_id"] == ws["tid"]
    if by_client_id:
        other = client.post(path, headers=other_keys["ingest"], json={"rating": 3})
        assert other.status_code == 201
        assert other.json()["feedback"]["trace_id"] == other_tid
    with SessionLocal() as db:
        rows = db.query(HumanFeedback).filter_by(trace_id=ws["tid"]).all()
        assert len(rows) == 1
        audit = db.query(AuditLog).filter_by(action="feedback.created", target_id=ws["tid"]).one()
        assert audit.organization_id == ws["org"]
        assert audit.actor_user_id is None
        assert audit.payload == {"feedback_id": rows[0].id, "actor_type": "api_key", "project_id": ws["pid"]}
        assert other_pid != audit.payload["project_id"]


def test_jwt_feedback_remains_audited_and_outsider_cannot_write(workspace):
    ws = workspace
    path = f"/v1/traces/{ws['tid']}/feedback"
    created = client.post(path, headers=ws["jwt"], json={"comment": "helpful"})
    assert created.status_code == 201
    with SessionLocal() as db:
        audit = db.query(AuditLog).filter_by(action="feedback.created").one()
        assert audit.actor_user_id == ws["user"]
        assert audit.payload == {"feedback_id": created.json()["feedback"]["id"]}
        db.add(User(id="usr_outside", email="outside@example.com", name="Outside"))
        db.commit()
    outsider = {"Authorization": "Bearer " + create_access_token(sub="usr_outside", email="outside@example.com", name="Outside")}
    assert client.post(path, headers=outsider, json={"rating": 5}).status_code == 404


@pytest.mark.parametrize("payload", [{}, {"comment": "  "}, {"thumbs": "left"}, {"rating": 0}, {"rating": 6}])
@pytest.mark.parametrize("trace_ref", ["by-client-id/ct_shared", "internal"])
def test_invalid_feedback_does_not_persist(workspace, payload, trace_ref):
    ws = workspace
    path = f"/v1/traces/{ws['tid'] if trace_ref == 'internal' else trace_ref}/feedback"
    assert client.post(path, headers=ws["keys"]["ingest"], json=payload).status_code == 422
    with SessionLocal() as db:
        assert db.query(HumanFeedback).count() == 0
        assert db.query(AuditLog).filter_by(action="feedback.created").count() == 0


def test_missing_and_deleted_traces_cannot_receive_feedback(workspace):
    ws = workspace
    assert client.post("/v1/traces/by-client-id/ct_pending/feedback", headers=ws["keys"]["ingest"], json={"rating": 5}).status_code == 404
    with SessionLocal() as db:
        db.get(Trace, ws["tid"]).deleted_at = datetime.now(timezone.utc)
        db.commit()
    for ref in (ws["tid"], "by-client-id/ct_shared"):
        assert client.post(f"/v1/traces/{ref}/feedback", headers=ws["keys"]["ingest"], json={"rating": 5}).status_code == 404
    with SessionLocal() as db:
        assert db.query(HumanFeedback).count() == 0


def test_sdk_captured_client_id_and_read_prompt_against_api(workspace, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "packages" / "sdk-python"))
    import evalops

    ws = workspace
    captured = []
    uploader = type("Capture", (), {"submit": lambda self, item: captured.append(item)})()
    tracer = evalops.tracer.EvalOpsTracer()
    tracer._disabled = False
    tracer._uploader = uploader
    monkeypatch.setattr(evalops, "_tracer", tracer)

    @evalops.trace("reply")
    def reply():
        return evalops.current_client_trace_id()

    cid = reply()
    assert cid == captured[0]["client_trace_id"]
    assert evalops.current_client_trace_id() is None
    monkeypatch.setattr("evalops.client.httpx.Client", lambda **kwargs: nullcontext(client))
    sdk = evalops.Client(api_key=ws["keys"]["ingest"]["X-EvalOps-Key"])
    with pytest.raises(httpx.HTTPStatusError) as pending:
        sdk.feedback(cid, thumbs="down")
    assert pending.value.response.status_code == 404
    ingested = client.post("/v1/traces", headers=ws["keys"]["ingest"], json={"traces": captured})
    tid = ingested.json()["results"][0]["trace_id"]
    assert sdk.feedback(cid, thumbs="up")["trace_id"] == tid
    prompt = client.post(f"/v1/projects/{ws['pid']}/prompts", headers=ws["jwt"], json={
        "slug": "managed", "template": "Hello {{name}}", "variables": {"name": "text"},
    }).json()["prompt"]["id"]
    reader = evalops.Client(api_key=ws["keys"]["read"]["X-EvalOps-Key"])
    assert reader.get_prompt(prompt)["template"] == "Hello {{name}}"
    assert reader.get_prompt(prompt, version=1)["version"] == 1
    with pytest.raises(httpx.HTTPStatusError) as forbidden:
        reader.feedback(cid, thumbs="up")
    assert forbidden.value.response.status_code == 403
