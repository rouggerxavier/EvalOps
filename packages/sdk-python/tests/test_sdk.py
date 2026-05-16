import evalops
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from evalops.uploader import BackgroundUploader, UploaderConfig


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

    def flush(self) -> None:
        return


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


def test_background_uploader_send_retries_non_2xx(monkeypatch) -> None:
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

    def _fake_send(traces: list[dict]) -> bool:
        sent_batches.append(len(traces))
        return True

    monkeypatch.setattr(uploader, "_send", _fake_send)

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

    def _always_fail_send(traces: list[dict]) -> bool:
        send_calls["n"] += 1
        return False

    monkeypatch.setattr(uploader, "_send", _always_fail_send)

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

    def _always_fail_send(traces: list[dict]) -> bool:
        return False

    monkeypatch.setattr(uploader, "_send", _always_fail_send)

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

    def _blocked_send(traces: list[dict]) -> bool:
        send_calls.append(traces)
        send_entered.set()
        release_send.wait(timeout=1.0)
        return False

    def _shutdown() -> None:
        try:
            uploader.shutdown()
        except BaseException as exc:
            shutdown_errors.append(exc)
        finally:
            shutdown_returned.set()

    monkeypatch.setattr(uploader, "_send", _blocked_send)

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


def test_background_uploader_queue_full_fallback_no_silent_drop(monkeypatch) -> None:
    uploader = BackgroundUploader(
        UploaderConfig(
            api_url="http://localhost:8000/v1",
            api_key="evk_prod_x",
            max_queue=1,
            flush_interval=60.0,
            submit_timeout_s=0.0,
            timeout=0.1,
        )
    )
    sent = {"n": 0}

    def _fake_send(traces: list[dict]) -> bool:
        sent["n"] += 1
        return True

    monkeypatch.setattr(uploader, "_send", _fake_send)

    try:
        uploader.submit({"client_trace_id": "ct_first"})
        uploader.submit({"client_trace_id": "ct_overflow"})
        assert sent["n"] >= 1  # fallback path executed
        assert uploader.dropped_count == 0
    finally:
        uploader.shutdown()
