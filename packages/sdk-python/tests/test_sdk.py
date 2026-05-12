import evalops
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread


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
