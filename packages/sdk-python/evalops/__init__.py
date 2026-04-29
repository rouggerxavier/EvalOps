from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Callable

from evalops.tracer import EvalOpsTracer

_tracer = EvalOpsTracer()


def ping() -> str:
    return "evalops-sdk-ok"


def init(
    *,
    api_key: str,
    project: str,
    environment: str = "dev",
    service: str | None = None,
    tags: dict | None = None,
    sample_rate: float = 1.0,
    disabled: bool = False,
    api_url: str = "http://localhost:8000/v1",
) -> None:
    _tracer.init(
        api_key=api_key,
        project=project,
        environment=environment,
        service=service,
        tags=tags,
        sample_rate=sample_rate,
        disabled=disabled,
        api_url=api_url,
    )


def trace(name: str) -> Callable:
    return _tracer.trace(name)


def span(name: str, type: str = "chain") -> AbstractContextManager[Any]:
    return _tracer.span(name=name, type=type)


def flush() -> None:
    _tracer.flush()


def instrument_openai() -> bool:
    try:
        from openai.resources.chat.completions import Completions
    except Exception:
        return False

    original = Completions.create
    if getattr(original, "__evalops_patched__", False):
        return True

    def wrapped(self: object, *args: object, **kwargs: object) -> object:
        with _tracer.span(name="openai.chat.completions", type="llm_call") as sp:
            model = kwargs.get("model")
            messages = kwargs.get("messages")
            if model is not None or messages is not None:
                sp.set_io(input={"model": model, "messages": messages})
            response = original(self, *args, **kwargs)
            sp.set_io(output={"response_type": response.__class__.__name__})
            return response

    setattr(wrapped, "__evalops_patched__", True)
    Completions.create = wrapped  # type: ignore[method-assign]
    return True
