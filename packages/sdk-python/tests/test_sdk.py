import evalops


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
