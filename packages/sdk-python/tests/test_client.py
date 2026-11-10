from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import sleep

import httpx
import pytest

from evalops import Client
from evalops.tracer import EvalOpsTracer


@pytest.fixture()
def server():
    events = []
    responses = []

    class Handler(BaseHTTPRequestHandler):
        def respond(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            events.append((self.command, self.path, self.headers.get("X-EvalOps-Key"), json.loads(body) if body else None))
            status, data, delay = responses.pop(0) if responses else (200, {}, 0)
            sleep(delay)
            self.send_response(status)
            self.end_headers()
            try:
                self.wfile.write(json.dumps(data).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

        do_GET = respond
        do_POST = respond

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=lambda: http.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http.server_port}/v1/", events, responses
    http.shutdown()
    http.server_close()
    thread.join(timeout=1)


def test_feedback_sends_real_http_payload_once(server):
    url, events, responses = server
    feedback = {"id": "fbk_1", "trace_id": "trc_1", "thumbs": "up"}
    responses.append((201, {"feedback": feedback}, 0))
    assert Client(api_key="ingest-key", api_url=url).feedback(
        "ct_1", thumbs="up", rating=5, comment="useful", tags=["human"], user_ref="opaque",
        correction={"text": "fixed"},
    ) == feedback
    assert events == [("POST", "/v1/traces/by-client-id/ct_1/feedback", "ingest-key", {
        "source": "sdk", "thumbs": "up", "rating": 5, "comment": "useful", "tags": ["human"],
        "user_ref": "opaque", "correction": {"text": "fixed"},
    })]


def test_get_prompt_uses_current_version_or_explicit_pin(server):
    url, events, responses = server
    old = {"version": 1, "template": "old"}
    current = {"version": 2, "template": "current", "variables": {"name": "text"}}
    responses.extend([(200, {"current_version": 2}, 0), (200, {"data": [old, current]}, 0),
                      (200, {"data": [old, current]}, 0)])
    client = Client(api_key="read-key", api_url=url)
    assert client.get_prompt("pmt_1") == current
    assert client.get_prompt("pmt_1", version=1) == old
    assert [(e[0], e[1], e[2]) for e in events] == [
        ("GET", "/v1/prompts/pmt_1", "read-key"),
        ("GET", "/v1/prompts/pmt_1/versions", "read-key"),
        ("GET", "/v1/prompts/pmt_1/versions", "read-key"),
    ]


@pytest.mark.parametrize("status", [401, 403, 404, 422])
@pytest.mark.parametrize("operation", ["get", "feedback"])
def test_http_errors_are_visible_without_retry(server, status, operation):
    url, events, responses = server
    responses.append((status, {"detail": "rejected"}, 0))
    with pytest.raises(httpx.HTTPStatusError) as error:
        client = Client(api_key="key", api_url=url)
        if operation == "get":
            client.get_prompt("pmt_1", version=1)
        else:
            client.feedback("ct_1", rating=6)
    assert error.value.response.status_code == status
    assert len(events) == 1


@pytest.mark.parametrize("status", [408, 429, 503])
def test_get_retries_transient_http_errors(server, monkeypatch, status):
    url, events, responses = server
    monkeypatch.setattr("evalops.client.sleep", lambda _: None)
    responses.extend([(status, {}, 0), (200, {"data": [{"version": 1, "template": "ok"}]}, 0)])
    assert Client(api_key="read-key", api_url=url).get_prompt("pmt_1", version=1)["template"] == "ok"
    assert len(events) == 2


def test_get_raises_after_retry_budget_and_post_never_retries(server, monkeypatch):
    url, events, responses = server
    monkeypatch.setattr("evalops.client.sleep", lambda _: None)
    responses.extend([(503, {}, 0)] * 4)
    client = Client(api_key="key", api_url=url)
    with pytest.raises(httpx.HTTPStatusError):
        client.get_prompt("pmt_1", version=1)
    assert len(events) == 3
    with pytest.raises(httpx.HTTPStatusError):
        client.feedback("ct_1", thumbs="up")
    assert len(events) == 4


@pytest.mark.parametrize("operation,attempts", [("get", 3), ("feedback", 1)])
def test_real_socket_timeout_is_bounded_and_propagated(server, monkeypatch, operation, attempts):
    url, events, responses = server
    monkeypatch.setattr("evalops.client.sleep", lambda _: None)
    responses.extend([(200, {}, 0.15)] * attempts)
    client = Client(api_key="key", api_url=url, timeout=0.03)
    with pytest.raises(httpx.TimeoutException):
        if operation == "get":
            client.get_prompt("pmt_1", version=1)
        else:
            client.feedback("ct_1", thumbs="up")
    assert len(events) == attempts


def test_missing_version_is_explicit(server):
    url, _, responses = server
    responses.append((200, {"data": [{"version": 1}]}, 0))
    with pytest.raises(LookupError, match="version 2"):
        Client(api_key="read-key", api_url=url).get_prompt("pmt_1", version=2)


@pytest.mark.parametrize("version", [0, -1, True, 1.5, "1"])
def test_version_must_be_a_positive_integer(version):
    with pytest.raises(ValueError):
        Client(api_key="key").get_prompt("pmt_1", version=version)


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_timeout_must_be_bounded(timeout):
    with pytest.raises(ValueError):
        Client(api_key="key", timeout=timeout)


def test_client_trace_id_is_captured_only_in_active_trace():
    tracer = EvalOpsTracer()
    assert tracer.current_client_trace_id() is None
    tracer._disabled = False
    captured = []
    tracer._uploader = type("Capture", (), {"submit": lambda self, item: captured.append(item)})()

    @tracer.trace("reply")
    def reply():
        cid = tracer.current_client_trace_id()
        with tracer.span("llm"):
            assert tracer.current_client_trace_id() == cid
        return cid

    cid = reply()
    assert cid == captured[0]["client_trace_id"]
    assert tracer.current_client_trace_id() is None
    tracer._sample_rate = 0
    assert reply() is None


def test_classification_evaluator_manifest_uses_same_result_contract(server):
    url, events, responses = server
    result = {"id": "evaluation", "decision": "inconclusive"}
    responses.append((201, result, 0))
    assert Client(api_key="task-key", api_url=url).evaluate("project", "predictions", evaluator="classification.standard", idempotency_key="operation") == result
    assert events[0][3] == {"prediction_set_id": "predictions", "evaluator": {"id": "classification.standard", "version": "1", "config": {}}}
