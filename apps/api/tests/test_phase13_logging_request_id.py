"""Phase 7C: structured logging + request_id middleware tests."""
from __future__ import annotations

import json
import logging

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

import app.main as main_app
from app.db import SessionLocal
from app.logging_config import _JsonFormatter
from app.main import app
from app.models import ApiKey, Membership, Organization, Project, User
from app.request_id import get_request_id, reset_request_context, set_request_context
from app.security import create_access_token, generate_api_key, hash_api_key, new_id

_VALID_ID = "test-req-0001"
_INVALID_CASES = [
    "id with spaces",
    "id\nwith\nnewlines",
    "id\x00null",
    "id\rwith\rCR",
    "<script>alert(1)</script>",
    "a" * 200,  # exceeds 128 chars
    "",
]


@app.get("/__phase13/context")
async def _phase13_context(request: Request) -> dict[str, str | None]:
    request.state.user_id = "usr_phase13"
    request.state.org_id = "org_phase13"
    return {"request_id": get_request_id()}


@app.get("/__phase13/unhandled")
async def _phase13_unhandled() -> None:
    raise RuntimeError("Bearer secret-token-value /home/x SELECT * FROM users")


@pytest.fixture(scope="module")
def client():
    # Do not use context manager: avoids anyio-plugin/portal interference
    # that causes BaseHTTPMiddleware to not run inside the pytest event loop.
    # Lifespan/DB setup runs lazily on first request.
    yield TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def access_events(monkeypatch):
    events: list[dict] = []

    def _capture(message: str, *args, **kwargs) -> None:
        events.append({"message": message, "extra": kwargs.get("extra", {})})

    monkeypatch.setattr(main_app.access_logger, "info", _capture)
    return events


@pytest.fixture()
def json_access_logs():
    lines: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(self.format(record))

    handler = _CaptureHandler()
    handler.setFormatter(_JsonFormatter())
    logger = main_app.access_logger
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        yield lines
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate


def _record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord("evalops.test", logging.INFO, __file__, 1, message, (), None)


def _request_end(events: list[dict]) -> dict:
    return next(event for event in events if event["message"] == "request.end")


def _seed_workspace() -> dict[str, str]:
    user_id = new_id("usr")
    org_id = new_id("org")
    project_id = new_id("prj")
    raw_key, prefix = generate_api_key("prod")
    with SessionLocal() as db:
        db.add_all(
            [
                User(id=user_id, email=f"{user_id}@example.com", name="Phase 13 User"),
                Organization(id=org_id, name="Phase 13 Org", slug=f"phase13-{org_id}"),
                Project(id=project_id, organization_id=org_id, name="Phase 13 Project", slug=f"phase13-{project_id}"),
                Membership(user_id=user_id, organization_id=org_id, role="owner"),
                ApiKey(
                    id=new_id("key"),
                    project_id=project_id,
                    prefix=prefix,
                    hash=hash_api_key(raw_key),
                    name="Phase 13 key",
                    environment="prod",
                    scopes="ingest",
                    rate_limit_per_minute=60,
                ),
            ]
        )
        db.commit()
    return {
        "user_id": user_id,
        "org_id": org_id,
        "project_id": project_id,
        "api_key": raw_key,
        "authorization": f"Bearer {create_access_token(sub=user_id, email=f'{user_id}@example.com', name='Phase 13 User')}",
    }


def test_request_id_generated_when_absent(client: TestClient):
    res = client.get("/health/liveness")
    assert res.status_code == 200
    rid = res.headers.get("x-request-id")
    assert rid is not None
    assert len(rid) > 0


def test_request_id_reused_when_valid(client: TestClient):
    res = client.get("/health/liveness", headers={"X-Request-ID": _VALID_ID})
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == _VALID_ID


@pytest.mark.parametrize("bad_id", _INVALID_CASES)
def test_invalid_request_id_replaced(client: TestClient, bad_id: str):
    res = client.get("/health/liveness", headers={"X-Request-ID": bad_id})
    assert res.status_code == 200
    rid = res.headers.get("x-request-id")
    assert rid is not None
    assert rid != bad_id or bad_id == ""
    assert "\n" not in rid
    assert " " not in rid
    assert "\r" not in rid
    assert len(rid) <= 128


def test_newline_injection_rejected(client: TestClient):
    for payload in ["legit\nX-Injected: evil", "a\rb", "foo\x00bar"]:
        res = client.get("/health/liveness", headers={"X-Request-ID": payload})
        assert res.status_code == 200
        rid = res.headers.get("x-request-id")
        assert rid is not None
        assert "\n" not in rid
        assert "\r" not in rid
        assert "\x00" not in rid
        assert rid != payload


def test_liveness_still_works(client: TestClient):
    res = client.get("/health/liveness")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_readiness_still_works(client: TestClient):
    res = client.get("/health/readiness")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_error_response_carries_request_id(client: TestClient):
    # unauthenticated → 401 before any DB access
    res = client.get("/v1/organizations")
    assert res.status_code == 401
    rid = res.headers.get("x-request-id")
    assert rid is not None
    assert len(rid) > 0


def test_error_response_reuses_client_request_id(client: TestClient):
    res = client.get("/v1/organizations", headers={"X-Request-ID": _VALID_ID})
    assert res.status_code == 401
    assert res.headers.get("x-request-id") == _VALID_ID


def test_json_formatter_outputs_json_with_context_request_id():
    tokens = set_request_context(request_id="rid_ctx", user_id="usr_ctx", org_id="org_ctx")
    try:
        record = _record("formatter.test")
        record.method = "GET"
        record.path = "/health/liveness"
        record.route = "/health/liveness"
        record.status_code = 200
        record.latency_ms = 1.2
        data = json.loads(_JsonFormatter().format(record))
    finally:
        reset_request_context(tokens)

    assert data["event"] == "formatter.test"
    assert data["msg"] == "formatter.test"
    assert isinstance(data["timestamp"], str)
    assert "ts" not in data
    assert data["request_id"] == "rid_ctx"
    assert data["user_id"] == "usr_ctx"
    assert data["org_id"] == "org_ctx"
    assert data["method"] == "GET"
    assert data["path"] == "/health/liveness"
    assert data["route"] == "/health/liveness"
    assert data["status_code"] == 200
    assert data["latency_ms"] == 1.2


def test_request_logs_start_and_end_with_request_fields(client: TestClient, access_events):
    res = client.get("/health/liveness", headers={"X-Request-ID": _VALID_ID})

    assert res.status_code == 200
    assert [event["message"] for event in access_events] == ["request.start", "request.end"]
    start, end = access_events
    assert start["extra"]["request_id"] == _VALID_ID
    assert start["extra"]["method"] == "GET"
    assert start["extra"]["path"] == "/health/liveness"
    assert end["extra"]["request_id"] == _VALID_ID
    assert end["extra"]["method"] == "GET"
    assert end["extra"]["path"] == "/health/liveness"
    assert end["extra"]["route"] == "/health/liveness"
    assert end["extra"]["status_code"] == 200
    assert isinstance(end["extra"]["latency_ms"], float)


def test_request_context_is_reset_between_requests(client: TestClient, access_events):
    first = client.get("/health/liveness", headers={"X-Request-ID": "rid_first"})
    second = client.get("/health/liveness", headers={"X-Request-ID": "rid_second"})

    assert first.status_code == 200
    assert second.status_code == 200
    end_ids = [event["extra"]["request_id"] for event in access_events if event["message"] == "request.end"]
    assert end_ids == ["rid_first", "rid_second"]
    assert get_request_id() is None


def test_request_logs_do_not_include_authorization_token_or_api_key(client: TestClient, access_events):
    secret_token = "secret-token-value"
    secret_key = "evalops_secret_api_key"
    res = client.get(
        "/health/liveness",
        headers={
            "Authorization": f"Bearer {secret_token}",
            "X-EvalOps-Key": secret_key,
            "X-Request-ID": _VALID_ID,
        },
    )

    assert res.status_code == 200
    serialized = json.dumps(access_events)
    assert "Authorization" not in serialized
    assert "X-EvalOps-Key" not in serialized
    assert secret_token not in serialized
    assert secret_key not in serialized


def test_unhandled_exception_log_error_is_sanitized(json_access_logs):
    local_client = TestClient(app, raise_server_exceptions=False)

    res = local_client.get("/__phase13/unhandled", headers={"X-Request-ID": _VALID_ID})

    assert res.status_code == 500
    entries = [json.loads(line) for line in json_access_logs]
    end = next(entry for entry in entries if entry["event"] == "request.end")
    assert end["status_code"] == 500
    assert end["error"] == "RuntimeError"
    serialized = json.dumps(entries)
    for leak in ("Bearer", "secret-token-value", "/home/x", "SELECT", "users"):
        assert leak not in serialized


def test_user_id_and_org_id_are_logged_when_request_state_has_them(client: TestClient, access_events):
    res = client.get("/__phase13/context", headers={"X-Request-ID": _VALID_ID})

    assert res.status_code == 200
    assert res.json()["request_id"] == _VALID_ID
    end = _request_end(access_events)
    assert end["extra"]["user_id"] == "usr_phase13"
    assert end["extra"]["org_id"] == "org_phase13"


def test_user_id_is_logged_from_authenticated_dependency(client: TestClient, access_events):
    workspace = _seed_workspace()

    res = client.get(
        "/v1/organizations",
        headers={"Authorization": workspace["authorization"], "X-Request-ID": _VALID_ID},
    )

    assert res.status_code == 200
    end = _request_end(access_events)
    assert end["extra"]["user_id"] == workspace["user_id"]


def test_org_id_is_logged_from_api_key_dependency(client: TestClient, access_events):
    workspace = _seed_workspace()

    res = client.post(
        "/v1/traces",
        headers={"X-EvalOps-Key": workspace["api_key"], "X-Request-ID": _VALID_ID},
        json={"traces": []},
    )

    assert res.status_code == 202
    end = _request_end(access_events)
    assert end["extra"]["org_id"] == workspace["org_id"]
