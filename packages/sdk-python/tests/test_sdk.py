import asyncio
import evalops
import json
import logging
import time
import subprocess
import sys
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from time import sleep
from types import ModuleType, SimpleNamespace

import pytest

from evalops.tracer import EvalOpsTracer
from evalops.uploader import BackgroundUploader, ReplayResult, UploaderConfig, _SendOutcome


def _assert_returns_within(fn, timeout_s: float = 1.0) -> None:
    raised: list[BaseException] = []

    def _run() -> None:
        try:
            fn()
        except BaseException as exc:
            raised.append(exc)

    caller = Thread(target=_run, daemon=True)
    caller.start()
    caller.join(timeout=timeout_s)
    assert not caller.is_alive(), f"{fn.__name__} did not return within {timeout_s}s"
    if raised:
        raise raised[0]


class DummyUploader:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def submit(self, payload: dict) -> None:
        self.items.append(payload)

    def flush(self, timeout: float = 5.0) -> bool:
        return True

    def shutdown(self, timeout: float = 5.0) -> bool:
        return True


def test_ping() -> None:
    assert evalops.ping() == "evalops-sdk-ok"


def test_disabled_mode_is_noop() -> None:
    evalops.init(api_key="evk_prod_x", project="proj", disabled=True)

    @evalops.trace("demo.trace")
    def handler(v: int) -> int:
        with evalops.span("inner", type="chain") as sp:
            sp.set_io(input={"v": v}, output={"v2": v * 2})
        return v * 2

    assert handler(2) == 4


def test_trace_decorator_submits_payload() -> None:
    evalops.init(api_key="evk_prod_x", project="proj", disabled=False)
    uploader = DummyUploader()
    evalops._tracer._uploader = uploader

    @evalops.trace("demo.trace")
    def handler(v: int) -> int:
        with evalops.span("inner", type="tool_call") as sp:
            sp.set_io(input={"v": v}, output={"ok": True})
        return v + 1

    assert handler(10) == 11
    assert len(uploader.items) == 1
    payload = uploader.items[0]
    assert payload["name"] == "demo.trace"
    assert payload["spans"][0]["name"] == "demo.trace"


def test_instrument_openai_is_safe_when_dep_missing() -> None:
    result = evalops.instrument_openai()
    assert isinstance(result, bool)


class _CaptureHandler(BaseHTTPRequestHandler):
    events: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        payload = json.loads(body)
        self.__class__.events.append({"path": self.path, "headers": dict(self.headers), "payload": payload})
        self.send_response(202)
        self.end_headers()
        self.wfile.write(b'{"ingested":1}')

    def log_message(self, format: str, *args: object) -> None:
        return


def test_sdk_smoke_real_http_integration() -> None:
    _CaptureHandler.events.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_port

    try:
        evalops.init(
            api_key="evk_prod_integration",
            project="docops",
            environment="prod",
            service="docops-api",
            api_url=f"http://127.0.0.1:{port}/v1",
            disabled=False,
        )

        @evalops.trace("docops.answer")
        def handler(msg: str) -> str:
            with evalops.span("retrieve", type="retrieval") as sp:
                sp.set_io(input={"query": msg}, output={"hits": 2})
            return "ok"

        assert handler("hello") == "ok"
        evalops.flush()

        assert len(_CaptureHandler.events) >= 1
        event = _CaptureHandler.events[-1]
        assert event["path"] == "/v1/traces"
        assert event["payload"]["traces"][0]["name"] == "docops.answer"
        assert len(event["payload"]["traces"][0]["spans"]) >= 1
    finally:
        if evalops._tracer._uploader is not None:
            evalops._tracer._uploader.shutdown()
            evalops._tracer._uploader = None
        server.shutdown()
        server.server_close()


def test_background_uploader_send_retries_after_exception(monkeypatch) -> None:
    calls = {"n": 0}

    class _Resp:
        status_code = 202

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("transient failure")
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_retries=2,
            retry_backoff_s=0.0,
        )
    )
    try:
        assert uploader._send([{"client_trace_id": "ct_1"}]) is True
        assert calls["n"] == 2
    finally:
        uploader.shutdown()


def test_background_uploader_send_retries_non_2xx(monkeypatch, tmp_path) -> None:
    calls = {"n": 0}

    class _Resp:
        status_code = 500

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_retries=2,
            retry_backoff_s=0.0,
            dead_letter_dir=tmp_path,
        )
    )
    try:
        assert uploader._send([{"client_trace_id": "ct_2"}]) is False
        assert calls["n"] == 3  # first try + 2 retries
    finally:
        uploader.shutdown()


def test_background_uploader_flush_drains_all_batches(monkeypatch) -> None:
    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_batch=2,
            flush_interval=60.0,
            timeout=0.1,
        )
    )
    sent_batches: list[int] = []

    def _fake_send(traces: list[dict]) -> _SendOutcome:
        sent_batches.append(len(traces))
        return _SendOutcome(ok=True)

    monkeypatch.setattr(uploader, "_send_with_outcome", _fake_send)

    try:
        for i in range(5):
            uploader.submit({"client_trace_id": f"ct_{i}"})
        uploader.flush()
        assert uploader.queue.empty()
        assert sent_batches == [2, 2, 1]
    finally:
        uploader.shutdown()


def test_flush_returns_after_final_send_failure_and_counts_drops(monkeypatch) -> None:
    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_batch=2,
            flush_interval=60.0,
            max_retries=0,
            retry_backoff_s=0.0,
            timeout=0.1,
        )
    )
    send_calls = {"n": 0}

    def _always_fail_send(traces: list[dict]) -> _SendOutcome:
        send_calls["n"] += 1
        return _SendOutcome(ok=False)

    monkeypatch.setattr(uploader, "_send_with_outcome", _always_fail_send)

    try:
        for i in range(3):
            uploader.submit({"client_trace_id": f"ct_flush_fail_{i}"})
        _assert_returns_within(uploader.flush, timeout_s=1.0)
        assert uploader.queue.empty()
        assert uploader.dropped_count == 3
        assert send_calls["n"] == 2
    finally:
        _assert_returns_within(uploader.shutdown, timeout_s=1.0)


def test_shutdown_returns_after_final_send_failure_and_counts_drops(monkeypatch) -> None:
    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_batch=2,
            flush_interval=60.0,
            max_retries=0,
            retry_backoff_s=0.0,
            timeout=0.1,
        )
    )

    def _always_fail_send(traces: list[dict]) -> _SendOutcome:
        return _SendOutcome(ok=False)

    monkeypatch.setattr(uploader, "_send_with_outcome", _always_fail_send)

    for i in range(3):
        uploader.submit({"client_trace_id": f"ct_shutdown_fail_{i}"})
    _assert_returns_within(uploader.shutdown, timeout_s=1.0)
    assert uploader.dropped_count == 3
    assert uploader.queue.empty()


def test_shutdown_waits_for_in_flight_send_before_returning(monkeypatch) -> None:
    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            flush_interval=0.01,
            max_retries=0,
            retry_backoff_s=0.0,
            timeout=0.1,
        )
    )
    send_entered = Event()
    release_send = Event()
    shutdown_returned = Event()
    shutdown_errors: list[BaseException] = []
    send_calls: list[list[dict]] = []

    def _blocked_send(traces: list[dict]) -> _SendOutcome:
        send_calls.append(traces)
        send_entered.set()
        release_send.wait(timeout=1.0)
        return _SendOutcome(ok=False)

    def _shutdown() -> None:
        try:
            uploader.shutdown()
        except BaseException as exc:
            shutdown_errors.append(exc)
        finally:
            shutdown_returned.set()

    monkeypatch.setattr(uploader, "_send_with_outcome", _blocked_send)

    try:
        uploader.submit({"client_trace_id": "ct_shutdown_in_flight"})
        assert send_entered.wait(timeout=1.0), "worker did not enter _send"

        caller = Thread(target=_shutdown, daemon=True)
        caller.start()
        assert not shutdown_returned.wait(timeout=0.05)

        release_send.set()
        caller.join(timeout=1.0)
        assert not caller.is_alive(), "shutdown did not return after in-flight send completed"
        if shutdown_errors:
            raise shutdown_errors[0]
        assert not uploader._thread.is_alive()
        assert uploader.queue.empty()
        assert len(send_calls) == 1, (
            "in-flight payload that fails during shutdown must not trigger a "
            f"second _send; got {len(send_calls)} calls"
        )
        assert uploader.dropped_count == 1
    finally:
        release_send.set()
        if not uploader._stop.is_set() or uploader._thread.is_alive():
            _assert_returns_within(uploader.shutdown, timeout_s=1.0)


def test_non_retryable_4xx_does_not_retry_unnecessarily(monkeypatch) -> None:
    calls = {"n": 0}

    class _Resp:
        status_code = 401

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_retries=3,
            retry_backoff_s=0.0,
            flush_interval=60.0,
            timeout=0.1,
        )
    )
    try:
        assert uploader._send([{"client_trace_id": "ct_non_retryable"}]) is False
        assert calls["n"] == 1

        uploader.submit({"client_trace_id": "ct_non_retryable_flush"})
        _assert_returns_within(uploader.flush, timeout_s=1.0)
        assert calls["n"] == 2
        assert uploader.dropped_count == 1
    finally:
        _assert_returns_within(uploader.shutdown, timeout_s=1.0)


def test_retry_exhausted_transient_failure_writes_dead_letter(monkeypatch, tmp_path) -> None:
    calls = {"n": 0}

    class _Resp:
        status_code = 503

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_secret",
            max_retries=1,
            retry_backoff_s=0.0,
            flush_interval=60.0,
            timeout=0.1,
            dead_letter_dir=tmp_path,
        )
    )
    try:
        assert uploader._send([{"client_trace_id": "ct_dead", "input": {"msg": "payload"}}]) is False
        files = list(tmp_path.glob("evalops-dead-letter-*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["trace_count"] == 1
        assert data["failure_kind"] == "retry_exhausted"
        assert data["http_status"] == 503
        assert data["api_url"] == "http://localhost:8000/v1"
        assert data["traces"][0]["client_trace_id"] == "ct_dead"
        file_text = files[0].read_text(encoding="utf-8")
        assert "evk_prod_secret" not in file_text
        assert "X-EvalOps-Key" not in file_text
        assert calls["n"] == 2
    finally:
        uploader.shutdown()


def test_retry_exhausted_exception_writes_dead_letter(monkeypatch, tmp_path) -> None:
    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_secret",
            max_retries=1,
            retry_backoff_s=0.0,
            flush_interval=60.0,
            timeout=0.1,
            dead_letter_dir=tmp_path,
        )
    )
    try:
        assert uploader._send([{"client_trace_id": "ct_exception_dead"}]) is False
        files = list(tmp_path.glob("evalops-dead-letter-*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["failure_kind"] == "retry_exhausted"
        assert "http_status" not in data
        assert data["traces"][0]["client_trace_id"] == "ct_exception_dead"
    finally:
        uploader.shutdown()


def test_retry_exhausted_408_and_429_write_dead_letter(monkeypatch, tmp_path) -> None:
    for status_code in (408, 429):
        dead_dir = tmp_path / str(status_code)

        class _Resp:
            def __init__(self, code: int) -> None:
                self.status_code = code

        class _Client:
            def __init__(self, *args, **kwargs) -> None:
                return None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def post(self, *args, **kwargs):
                return _Resp(status_code)

        monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

        uploader = BackgroundUploader(
            UploaderConfig(
                api_url="http://localhost:8000/v1",
                api_key="evk_prod_x",
                max_retries=0,
                retry_backoff_s=0.0,
                flush_interval=60.0,
                timeout=0.1,
                dead_letter_dir=dead_dir,
            )
        )
        try:
            assert uploader._send([{"client_trace_id": f"ct_{status_code}_dead"}]) is False
            files = list(dead_dir.glob("evalops-dead-letter-*.json"))
            assert len(files) == 1
            data = json.loads(files[0].read_text(encoding="utf-8"))
            assert data["http_status"] == status_code
            assert data["traces"][0]["client_trace_id"] == f"ct_{status_code}_dead"
        finally:
            uploader.shutdown()


def test_dead_letter_api_url_metadata_strips_userinfo_query_and_fragment(
    monkeypatch,
    tmp_path,
) -> None:
    def _failed_send(traces, config) -> _SendOutcome:
        return _SendOutcome(ok=False, should_dead_letter=True, http_status=503)

    monkeypatch.setattr("evalops.uploader._send_traces", _failed_send)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="https://alice:password@example.com/v1?api_key=secret#token",
            api_key="evk_prod_secret",
            max_retries=0,
            flush_interval=60.0,
            timeout=0.1,
            dead_letter_dir=tmp_path,
        )
    )
    try:
        assert uploader._send([{"client_trace_id": "ct_api_url_sanitized"}]) is False
        files = list(tmp_path.glob("evalops-dead-letter-*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        file_text = files[0].read_text(encoding="utf-8")
        assert data["api_url"] == "https://example.com/v1"
        assert "?" not in data["api_url"]
        assert "#" not in data["api_url"]
        assert "alice" not in file_text
        assert "password" not in file_text
        assert "api_key" not in file_text
        assert "secret" not in file_text
        assert "token" not in file_text
    finally:
        uploader.shutdown()


def test_dead_letter_dir_env_override(monkeypatch, tmp_path) -> None:
    dead_dir = tmp_path / "env-dead"
    monkeypatch.setenv("EVALOPS_DEAD_LETTER_DIR", str(dead_dir))

    class _Resp:
        status_code = 500

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_retries=0,
            flush_interval=60.0,
            timeout=0.1,
        )
    )
    try:
        assert uploader._send([{"client_trace_id": "ct_env_dead"}]) is False
        assert len(list(dead_dir.glob("evalops-dead-letter-*.json"))) == 1
    finally:
        uploader.shutdown()


def test_permanent_4xx_does_not_write_dead_letter(monkeypatch, tmp_path) -> None:
    calls = {"n": 0}

    class _Resp:
        status_code = 422

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            calls["n"] += 1
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_retries=3,
            retry_backoff_s=0.0,
            flush_interval=60.0,
            timeout=0.1,
            dead_letter_dir=tmp_path,
        )
    )
    try:
        uploader.submit({"client_trace_id": "ct_permanent"})
        _assert_returns_within(uploader.flush, timeout_s=1.0)
        assert calls["n"] == 1
        assert uploader.dropped_count == 1
        assert list(tmp_path.glob("evalops-dead-letter-*.json")) == []
    finally:
        _assert_returns_within(uploader.shutdown, timeout_s=1.0)


def test_requeueable_transient_failure_does_not_write_dead_letter(monkeypatch, tmp_path) -> None:
    class _Resp:
        status_code = 503

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)
    monkeypatch.setattr(BackgroundUploader, "_loop", lambda self: None)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_retries=0,
            retry_backoff_s=0.0,
            flush_interval=60.0,
            timeout=0.1,
            dead_letter_dir=tmp_path,
        )
    )
    try:
        uploader.queue.put_nowait({"client_trace_id": "ct_requeue"})
        assert uploader._send_buffered(requeue_on_failure=True) is True
        assert uploader.dropped_count == 0
        assert not uploader.queue.empty()
        assert list(tmp_path.glob("evalops-dead-letter-*.json")) == []
    finally:
        if not uploader.queue.empty():
            uploader.queue.get_nowait()
        _assert_returns_within(uploader.shutdown, timeout_s=1.0)


def test_dead_letter_write_error_does_not_raise_or_log_payload(
    monkeypatch,
    tmp_path,
    caplog,
) -> None:
    class _Resp:
        status_code = 503

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            return _Resp()

    def _replace_fails(*args, **kwargs) -> None:
        raise OSError("disk path contains ct_secret_payload")

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)
    monkeypatch.setattr("evalops.uploader.os.replace", _replace_fails)

    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_secret",
            max_retries=0,
            flush_interval=60.0,
            timeout=0.1,
            dead_letter_dir=tmp_path,
        )
    )
    try:
        with caplog.at_level("WARNING", logger="evalops.uploader"):
            assert uploader._send([{"client_trace_id": "ct_secret_payload"}]) is False
        assert "ct_secret_payload" not in caplog.text
        assert "evk_prod_secret" not in caplog.text
        assert "OSError" in caplog.text
    finally:
        uploader.shutdown()


def test_replay_dead_letter_uses_explicit_api_url_and_removes_file(monkeypatch, tmp_path) -> None:
    dead_file = tmp_path / "evalops-dead-letter-test.json"
    dead_file.write_text(
        json.dumps(
            {
                "version": 1,
                "created_at": "2026-05-17T00:00:00Z",
                "api_url": "http://malicious.local/v1",
                "trace_count": 1,
                "failure_kind": "retry_exhausted",
                "http_status": 503,
                "traces": [{"client_trace_id": "ct_replay"}],
            }
        ),
        encoding="utf-8",
    )
    posts: list[dict] = []

    class _Resp:
        status_code = 202

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, url, *, headers, json):
            posts.append({"url": url, "headers": headers, "json": json})
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    result = evalops.replay_dead_letter(
        path=dead_file,
        api_url="http://safe.local/v1",
        api_key="evk_prod_replay",
    )

    assert result.files_seen == 1
    assert result.replayed == 1
    assert result.failed == 0
    assert result.removed == 1
    assert result.skipped == 0
    assert result.errors == []
    assert not dead_file.exists()
    assert posts[0]["url"] == "http://safe.local/v1/traces"
    assert posts[0]["json"]["traces"][0]["client_trace_id"] == "ct_replay"
    assert posts[0]["headers"]["X-EvalOps-Key"] == "evk_prod_replay"


def test_replay_dead_letter_keeps_file_when_send_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("evalops.uploader.sleep", lambda seconds: None)
    dead_file = tmp_path / "evalops-dead-letter-test.json"
    dead_file.write_text(
        json.dumps(
            {
                "version": 1,
                "created_at": "2026-05-17T00:00:00Z",
                "trace_count": 1,
                "failure_kind": "retry_exhausted",
                "traces": [{"client_trace_id": "ct_replay_failed"}],
            }
        ),
        encoding="utf-8",
    )

    class _Resp:
        status_code = 503

    class _Client:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def post(self, *args, **kwargs):
            return _Resp()

    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)

    result = evalops.replay_dead_letter(
        path=dead_file,
        api_url="http://safe.local/v1",
        api_key="evk_prod_replay",
    )

    assert result.files_seen == 1
    assert result.replayed == 0
    assert result.failed == 1
    assert result.removed == 0
    assert dead_file.exists()


def test_replay_dead_letter_uses_current_config_when_credentials_omitted(
    monkeypatch,
    tmp_path,
) -> None:
    calls: dict[str, object] = {}

    def _replay_stub(path=None, *, api_url, api_key, dead_letter_dir=None) -> ReplayResult:
        calls["path"] = path
        calls["api_url"] = api_url
        calls["api_key"] = api_key
        calls["dead_letter_dir"] = dead_letter_dir
        return ReplayResult(replayed=1)

    class _Uploader:
        config = UploaderConfig(api_url="http://current.local/v1", api_key="evk_prod_current")

    previous_uploader = evalops._tracer._uploader
    monkeypatch.setattr(evalops, "_replay_dead_letter", _replay_stub)
    evalops._tracer._uploader = _Uploader()
    try:
        result = evalops.replay_dead_letter(path=tmp_path / "evalops-dead-letter-test.json")
    finally:
        evalops._tracer._uploader = previous_uploader

    assert result.replayed == 1
    assert calls["api_url"] == "http://current.local/v1"
    assert calls["api_key"] == "evk_prod_current"


def test_replay_dead_letter_skips_invalid_unknown_and_unexpected_files(tmp_path) -> None:
    invalid_json = tmp_path / "evalops-dead-letter-invalid.json"
    unknown_version = tmp_path / "evalops-dead-letter-unknown.json"
    unexpected_file = tmp_path / "notes.json"
    invalid_json.write_text("{", encoding="utf-8")
    unknown_version.write_text(json.dumps({"version": 999, "traces": []}), encoding="utf-8")
    unexpected_file.write_text("{}", encoding="utf-8")

    result = evalops.replay_dead_letter(
        dead_letter_dir=tmp_path,
        api_url="http://safe.local/v1",
        api_key="evk_prod_replay",
    )

    assert result.files_seen == 2
    assert result.replayed == 0
    assert result.failed == 0
    assert result.skipped == 2
    assert unexpected_file.exists()
    assert any("invalid JSON" in error for error in result.errors)
    assert any("unsupported dead-letter version" in error for error in result.errors)


class _StatusClient:
    """httpx.Client stand-in that answers every POST with a fixed status."""

    status = 401
    calls = 0

    def __init__(self, *args, **kwargs) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def post(self, *args, **kwargs):
        type(self).calls += 1
        return type("Resp", (), {"status_code": type(self).status})()


@pytest.mark.parametrize("status", [401, 402, 413, 422])
def test_permanent_4xx_stops_sending_the_batch(monkeypatch, tmp_path, status) -> None:
    client = type("Client", (_StatusClient,), {"status": status, "calls": 0})
    monkeypatch.setattr("evalops.uploader.httpx.Client", client)
    uploader = BackgroundUploader(
        UploaderConfig(api_url="http://x/v1", api_key="k", flush_interval=0.01, dead_letter_dir=tmp_path)
    )
    try:
        uploader.submit({"client_trace_id": "ct"})
        sleep(0.3)
        assert client.calls == 1
        assert uploader.dropped_count == 1
        assert uploader.queue.empty()
    finally:
        _assert_returns_within(uploader.shutdown, timeout_s=1.0)


def test_transient_failure_backs_off_keeps_the_batch_and_recovers(monkeypatch, tmp_path) -> None:
    client = type("Client", (_StatusClient,), {"status": 503, "calls": 0})
    monkeypatch.setattr("evalops.uploader.httpx.Client", client)
    uploader = BackgroundUploader(
        UploaderConfig(api_url="http://x/v1", api_key="k", flush_interval=0.1, max_retries=0, dead_letter_dir=tmp_path)
    )
    try:
        uploader.submit({"client_trace_id": "ct"})
        sleep(0.7)
        # Delays of 0.1, 0.2 and 0.4 s fit in the window; without backoff this is thousands of calls.
        assert 1 <= client.calls <= 5
        assert uploader.dropped_count == 0
        client.status = 202
        sleep(0.9)
        assert uploader.queue.empty()
        assert uploader.dropped_count == 0
        assert uploader._retry_delay == 0.0
    finally:
        _assert_returns_within(uploader.shutdown, timeout_s=1.0)


def test_init_rejects_environment_the_api_refuses() -> None:
    with pytest.raises(ValueError, match="environment"):
        EvalOpsTracer().init(api_key="k", project="p", environment="production", disabled=True)


def test_set_llm_reaches_the_payload_and_survives_odd_values() -> None:
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", disabled=True)
    tracer._disabled = False
    tracer._uploader = DummyUploader()

    @tracer.trace("t")
    def run() -> None:
        with tracer.span("llm") as sp:
            sp.set_llm(
                provider="openrouter",
                model="m",
                messages_in=[{"role": "user", "content": "oi"}, "não é objeto"],
                messages_out=[{"role": "assistant", "content": "olá"}],
                tokens_in="10",
                tokens_out="não é número",
                cost_usd=Decimal("0.5"),
                prompt_version_ref="p@1",
            )

    run()
    span = next(s for s in tracer._uploader.items[0]["spans"] if s["name"] == "llm")
    assert span["type"] == "llm_call"
    assert (span["provider"], span["model"], span["prompt_version_ref"]) == ("openrouter", "m", "p@1")
    assert span["messages_in"] == [{"role": "user", "content": "oi"}]
    assert span["messages_out"] == [{"role": "assistant", "content": "olá"}]
    assert (span["tokens_in"], span["tokens_out"], span["cost_usd"]) == (10, None, 0.5)
    json.dumps(span)


def test_instrument_openai_records_the_call(monkeypatch) -> None:
    usage = SimpleNamespace(prompt_tokens=7, completion_tokens=3)
    response = SimpleNamespace(
        model="gpt-4o-mini",
        usage=usage,
        choices=[SimpleNamespace(message=SimpleNamespace(content="olá"))],
    )

    class Completions:
        def create(self, *args, **kwargs):
            return response

    module = ModuleType("openai.resources.chat.completions")
    module.Completions = Completions
    monkeypatch.setitem(sys.modules, "openai.resources.chat.completions", module)
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", disabled=True)
    tracer._disabled = False
    tracer._uploader = DummyUploader()
    monkeypatch.setattr(evalops, "_tracer", tracer)

    assert evalops.instrument_openai() is True

    @tracer.trace("t")
    def run() -> None:
        Completions().create(model="gpt-4o-mini", messages=[{"role": "user", "content": "oi"}])

    run()
    span = next(s for s in tracer._uploader.items[0]["spans"] if s["name"] == "openai.chat.completions")
    assert (span["provider"], span["model"], span["tokens_in"], span["tokens_out"]) == ("openai", "gpt-4o-mini", 7, 3)
    assert span["messages_in"] == [{"role": "user", "content": "oi"}]
    assert span["messages_out"] == [{"role": "assistant", "content": "olá"}]


def test_queued_traces_are_sent_at_process_exit() -> None:
    _CaptureHandler.events = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    script = f"""
import evalops
evalops.init(api_key="k", project="p", api_url="http://127.0.0.1:{server.server_port}/v1")
@evalops.trace("na.saida")
def run():
    return "ok"
run()
"""
    try:
        done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=20)
        assert done.returncode == 0, done.stderr
        names = [t["name"] for event in _CaptureHandler.events for t in event["payload"]["traces"]]
        assert names == ["na.saida"]
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_set_trace_describes_only_the_current_trace() -> None:
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", tags={"app": "x"}, disabled=True)
    tracer._disabled = False
    tracer._uploader = DummyUploader()
    tracer.set_trace(conversation_id="fora")

    @tracer.trace("t")
    def run() -> None:
        tracer.set_trace(conversation_id=123, batch="b1", user_ref="u1", tags={"canal": "wa"}, metadata={"sdk": "x", "k": "v"})

    run()
    run_again = tracer.trace("t2")(lambda: None)
    run_again()
    first, second = tracer._uploader.items
    assert first["metadata"]["conversation_id"] == "123"
    assert first["metadata"]["batch"] == "b1"
    assert first["metadata"]["k"] == "v"
    assert first["metadata"]["sdk"]["name"] == "evalops-python"
    assert first["user_ref"] == "u1"
    assert first["tags"] == {"app": "x", "canal": "wa"}
    assert second["tags"] == {"app": "x"}
    assert "conversation_id" not in second["metadata"]


def test_async_trace_records_real_duration_spans_and_output() -> None:
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", disabled=True)
    tracer._disabled = False
    uploader = DummyUploader()
    tracer._uploader = uploader

    async def lookup(key: str) -> str:
        with tracer.span(f"lookup.{key}", type="tool_call") as sp:
            await asyncio.sleep(0.02)
            sp.set_io(output={"key": key})
        return key

    @tracer.trace("async.turn")
    async def turn(msg: str) -> dict:
        with tracer.span("llm.generate", type="llm_call"):
            await asyncio.sleep(0.05)
        found = await asyncio.gather(lookup("a"), lookup("b"))
        return {"reply": msg.upper(), "found": found}

    assert asyncio.run(turn("oi")) == {"reply": "OI", "found": ["a", "b"]}
    assert len(uploader.items) == 1
    payload = uploader.items[0]
    root, *children = payload["spans"]
    assert root["output"] == {"result": {"reply": "OI", "found": ["a", "b"]}}
    duration = _parse(payload["ended_at"]) - _parse(payload["started_at"])
    assert duration >= 0.07
    assert sorted(span["name"] for span in children) == ["llm.generate", "lookup.a", "lookup.b"]
    assert all(span["parent_client_span_id"] == root["client_span_id"] for span in children)


def test_async_trace_records_the_error_and_reraises() -> None:
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", disabled=True)
    tracer._disabled = False
    uploader = DummyUploader()
    tracer._uploader = uploader

    @tracer.trace("async.fails")
    async def fails() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        asyncio.run(fails())
    assert uploader.items[0]["status"] == "error"
    assert uploader.items[0]["metadata"]["error"] == {"type": "RuntimeError", "message": "boom"}


def _parse(value: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(value).timestamp()


def test_full_queue_drops_without_blocking_the_caller(monkeypatch, caplog) -> None:
    release = Event()

    def _stuck_send(traces: list[dict]) -> _SendOutcome:
        release.wait(timeout=5.0)
        return _SendOutcome(ok=True)

    uploader = BackgroundUploader(
        UploaderConfig(api_url="http://x/v1", api_key="k", max_queue=1, max_batch=1, flush_interval=0.01)
    )
    monkeypatch.setattr(uploader, "_send_with_outcome", _stuck_send)
    try:
        uploader.submit({"client_trace_id": "ct_in_flight"})
        deadline = time.monotonic() + 1.0
        while not uploader.queue.empty() and time.monotonic() < deadline:
            sleep(0.01)
        uploader.submit({"client_trace_id": "ct_queued"})
        caplog.set_level(logging.WARNING, logger="evalops.uploader")
        started = time.monotonic()
        for i in range(20):
            uploader.submit({"client_trace_id": f"ct_overflow_{i}"})
        assert time.monotonic() - started < 0.1
        assert uploader.dropped_count == 20
        assert "queue full" in caplog.text
    finally:
        release.set()
        _assert_returns_within(uploader.shutdown, timeout_s=2.0)


def test_2xx_with_errors_logs_each_rejected_trace(monkeypatch, caplog) -> None:
    body = {
        "ingested": 1,
        "errors": [
            {"index": 1, "client_trace_id": "ct_bad", "message": "ingest_failed"},
            {"index": 2, "client_trace_id": "ct_worse", "message": "ingest_failed"},
        ],
    }
    client = type(
        "Client",
        (_StatusClient,),
        {"status": 202, "calls": 0, "post": lambda self, *a, **k: SimpleNamespace(status_code=202, json=lambda: body)},
    )
    monkeypatch.setattr("evalops.uploader.httpx.Client", client)
    caplog.set_level(logging.WARNING, logger="evalops.uploader")
    uploader = BackgroundUploader(UploaderConfig(api_url="http://x/v1", api_key="k", flush_interval=60.0))
    try:
        uploader.submit({"client_trace_id": "ct_ok"})
        assert uploader.flush(timeout=1.0) is True
        assert "ct_bad" in caplog.text and "ct_worse" in caplog.text
        assert "ct_ok" not in caplog.text
    finally:
        _assert_returns_within(uploader.shutdown, timeout_s=1.0)


def test_retries_resend_the_same_client_trace_id(monkeypatch) -> None:
    sent: list[str] = []

    class _Client(_StatusClient):
        def post(self, *args, **kwargs):
            sent.extend(t["client_trace_id"] for t in kwargs["json"]["traces"])
            return SimpleNamespace(status_code=503 if len(sent) < 3 else 202, json=lambda: {})

    monkeypatch.setattr("evalops.uploader.sleep", lambda seconds: None)
    monkeypatch.setattr("evalops.uploader.httpx.Client", _Client)
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", api_url="http://x/v1")

    @tracer.trace("retry.turn")
    def turn() -> str:
        return "ok"

    try:
        turn()
        assert tracer.flush(timeout=2.0) is True
        assert len(sent) == 3
        assert len(set(sent)) == 1 and sent[0].startswith("ct_")
        turn()
        assert tracer.flush(timeout=2.0) is True
        assert sent[3] != sent[0]
    finally:
        _assert_returns_within(tracer.shutdown, timeout_s=2.0)


def test_shutdown_sends_pending_traces() -> None:
    _CaptureHandler.events = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", api_url=f"http://127.0.0.1:{server.server_port}/v1")
    tracer._uploader.config.flush_interval = 60.0

    @tracer.trace("pending.turn")
    def turn() -> str:
        return "ok"

    try:
        turn()
        assert tracer.shutdown(timeout=2.0) is True
        names = [t["name"] for event in _CaptureHandler.events for t in event["payload"]["traces"]]
        assert names == ["pending.turn"]
    finally:
        server.shutdown()
        server.server_close()


def test_shutdown_is_bounded_and_dead_letters_what_it_could_not_send(monkeypatch, tmp_path) -> None:
    release = Event()

    def _stuck_send(traces: list[dict]) -> _SendOutcome:
        release.wait(timeout=5.0)
        return _SendOutcome(ok=True)

    uploader = BackgroundUploader(
        UploaderConfig(api_url="http://x/v1", api_key="k", max_batch=1, flush_interval=0.01, dead_letter_dir=tmp_path)
    )
    monkeypatch.setattr(uploader, "_send_with_outcome", _stuck_send)
    try:
        for i in range(3):
            uploader.submit({"client_trace_id": f"ct_{i}"})
        assert uploader.flush(timeout=0.1) is False
        started = time.monotonic()
        assert uploader.shutdown(timeout=0.2) is False
        assert time.monotonic() - started < 1.0
        files = list(tmp_path.glob("evalops-dead-letter-*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["failure_kind"] == "shutdown_timeout"
        # ct_0 was in flight in the stuck send, not in the queue.
        assert [t["client_trace_id"] for t in data["traces"]] == ["ct_0", "ct_1", "ct_2"]
        assert uploader.dropped_count == 3
    finally:
        release.set()


def _capture_tracer() -> tuple:
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", disabled=True)
    tracer._disabled = False
    uploader = DummyUploader()
    tracer._uploader = uploader
    return tracer, uploader


class _BadRepr:
    def __repr__(self) -> str:
        raise RuntimeError("repr boom")


@pytest.mark.parametrize(
    "odd, expected",
    [(float("nan"), None), (float("inf"), None), (float("-inf"), None), (_BadRepr(), "<_BadRepr>")],
    ids=["nan", "inf", "-inf", "raising-repr"],
)
def test_odd_values_never_break_the_call_and_the_trace_still_arrives(odd, expected) -> None:
    tracer, uploader = _capture_tracer()

    @tracer.trace("odd.turn")
    def turn(value: object) -> object:
        with tracer.span("llm") as sp:
            sp.set_io(input={"value": value})
            sp.set_llm(tokens_in=value, tokens_out=value, cost_usd=value)
        tracer.set_trace(metadata={"value": value})
        return value

    assert turn(odd) is odd
    assert len(uploader.items) == 1
    payload = uploader.items[0]
    root, llm = payload["spans"]
    assert root["input"] == {"args": [expected], "kwargs": {}}
    assert root["output"] == {"result": expected}
    assert llm["input"] == {"value": expected}
    assert llm["tokens_in"] is None and llm["tokens_out"] is None and llm["cost_usd"] is None
    assert payload["metadata"]["value"] == expected
    json.dumps(payload, allow_nan=False)


def test_payload_failure_keeps_the_original_exception(monkeypatch, caplog) -> None:
    tracer, uploader = _capture_tracer()

    def _broken(self) -> dict:
        raise RuntimeError("payload boom")

    monkeypatch.setattr("evalops.tracer.TraceRecord.to_payload", _broken)
    caplog.set_level(logging.WARNING, logger="evalops.tracer")

    @tracer.trace("broken.payload")
    def turn() -> None:
        raise ValueError("original")

    with pytest.raises(ValueError, match="original"):
        turn()
    assert uploader.items == []
    assert "could not build trace payload" in caplog.text


def test_trace_rejects_sync_and_async_generators() -> None:
    tracer, _ = _capture_tracer()

    def gen():
        yield 1

    async def agen():
        yield 1

    for func in (gen, agen):
        with pytest.raises(TypeError, match="generator"):
            tracer.trace("gen")(func)


def test_cancelled_async_trace_is_recorded_as_error() -> None:
    tracer, uploader = _capture_tracer()

    @tracer.trace("async.cancelled")
    async def slow() -> None:
        with tracer.span("wait"):
            await asyncio.sleep(10)

    async def main() -> None:
        task = asyncio.ensure_future(slow())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(main())
    payload = uploader.items[0]
    assert payload["status"] == "error"
    assert payload["metadata"]["error"]["type"] == "CancelledError"
    assert all(span["status"] == "error" for span in payload["spans"])


def test_span_after_the_trace_closed_is_a_noop() -> None:
    tracer, uploader = _capture_tracer()
    later: list = []

    @tracer.trace("leaky.turn")
    async def turn() -> None:
        later.append(asyncio.ensure_future(late_span()))

    async def late_span() -> None:
        await asyncio.sleep(0.01)
        with tracer.span("too.late") as sp:
            sp.set_io(output={"x": 1})

    async def main() -> None:
        await turn()
        await later[0]

    asyncio.run(main())
    assert [span["name"] for span in uploader.items[0]["spans"]] == ["leaky.turn"]


def test_submit_after_shutdown_goes_to_dead_letter(tmp_path) -> None:
    uploader = BackgroundUploader(UploaderConfig(api_url="http://x/v1", api_key="k", dead_letter_dir=tmp_path))
    assert uploader.shutdown(timeout=1.0) is True
    uploader.submit({"client_trace_id": "ct_late"})
    files = list(tmp_path.glob("evalops-dead-letter-*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["failure_kind"] == "after_shutdown"
    assert data["traces"] == [{"client_trace_id": "ct_late"}]
    assert uploader.dropped_count == 1
    assert uploader.queue.empty()


def test_dropped_count_is_exact_under_concurrent_submits(monkeypatch) -> None:
    release = Event()

    def _stuck_send(traces: list[dict]) -> _SendOutcome:
        release.wait(timeout=5.0)
        return _SendOutcome(ok=True)

    uploader = BackgroundUploader(
        UploaderConfig(api_url="http://x/v1", api_key="k", max_queue=1, max_batch=1, flush_interval=0.01)
    )
    monkeypatch.setattr(uploader, "_send_with_outcome", _stuck_send)
    monkeypatch.setattr("evalops.uploader.logger.warning", lambda *a, **k: None)
    try:
        uploader.submit({"client_trace_id": "ct_in_flight"})
        deadline = time.monotonic() + 1.0
        while not uploader.queue.empty() and time.monotonic() < deadline:
            sleep(0.01)
        uploader.submit({"client_trace_id": "ct_queued"})

        def _burst() -> None:
            for i in range(2000):
                uploader.submit({"client_trace_id": f"ct_{i}"})

        threads = [Thread(target=_burst) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert uploader.dropped_count == 16000
    finally:
        release.set()
        _assert_returns_within(uploader.shutdown, timeout_s=2.0)


def test_second_init_shuts_down_the_old_uploader(tmp_path) -> None:
    tracer = EvalOpsTracer()
    tracer.init(api_key="k", project="p", api_url="http://127.0.0.1:9/v1")
    old = tracer._uploader
    tracer.init(api_key="k", project="p", disabled=True)
    assert tracer._uploader is None
    assert old._stop.is_set()
    assert not old._thread.is_alive()


def test_instrument_openai_does_not_trace_streams(monkeypatch) -> None:
    calls: list[dict] = []

    class Completions:
        def create(self, *args, **kwargs):
            calls.append(kwargs)
            return iter(["chunk"])

    completions = ModuleType("openai.resources.chat.completions")
    completions.Completions = Completions
    for name in ("openai", "openai.resources", "openai.resources.chat"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    monkeypatch.setitem(sys.modules, "openai.resources.chat.completions", completions)
    tracer, uploader = _capture_tracer()
    monkeypatch.setattr(evalops, "_tracer", tracer)
    assert evalops.instrument_openai() is True

    @tracer.trace("stream.turn")
    def turn() -> list:
        return list(Completions().create(model="m", messages=[], stream=True))

    assert turn() == ["chunk"]
    assert calls == [{"model": "m", "messages": [], "stream": True}]
    assert [span["name"] for span in uploader.items[0]["spans"]] == ["stream.turn"]
