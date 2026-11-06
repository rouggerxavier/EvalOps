from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Callable

from evalops.tracer import EvalOpsTracer
from evalops.uploader import DEFAULT_TIMEOUT_S, ReplayResult, replay_dead_letter as _replay_dead_letter

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


def set_trace(
    *,
    conversation_id: str | None = None,
    batch: str | None = None,
    user_ref: str | None = None,
    tags: dict | None = None,
    metadata: dict | None = None,
) -> None:
    _tracer.set_trace(conversation_id=conversation_id, batch=batch, user_ref=user_ref, tags=tags, metadata=metadata)


def flush(timeout: float = DEFAULT_TIMEOUT_S) -> bool:
    """Wait up to ``timeout`` seconds for queued traces to be sent. False if some are still pending."""
    return _tracer.flush(timeout)


def shutdown(timeout: float = DEFAULT_TIMEOUT_S) -> bool:
    """Stop the uploader within ``timeout`` seconds; unsent traces go to dead-letter.

    Also runs at normal process exit. False if something was left unsent.
    """
    return _tracer.shutdown(timeout)


def replay_dead_letter(
    path: str | Path | None = None,
    *,
    api_url: str | None = None,
    api_key: str | None = None,
    dead_letter_dir: str | Path | None = None,
) -> ReplayResult:
    config = _tracer._uploader.config if _tracer._uploader is not None else None
    resolved_api_url = api_url or (config.api_url if config is not None else None)
    resolved_api_key = api_key or (config.api_key if config is not None else None)
    if resolved_api_url is None:
        return ReplayResult(errors=["api_url is required when evalops is not initialized"])
    if resolved_api_key is None:
        return ReplayResult(errors=["api_key is required when evalops is not initialized"])
    return _replay_dead_letter(
        path=path,
        api_url=resolved_api_url,
        api_key=resolved_api_key,
        dead_letter_dir=dead_letter_dir,
    )


def instrument_openai() -> bool:
    try:
        from openai.resources.chat.completions import Completions
    except Exception:
        return False

    original = Completions.create
    if getattr(original, "__evalops_patched__", False):
        return True

    def wrapped(self: object, *args: object, **kwargs: object) -> object:
        if kwargs.get("stream"):
            # shortcut: streams are not traced (the reply only exists after the caller drains it); record it with set_llm.
            return original(self, *args, **kwargs)
        with _tracer.span(name="openai.chat.completions", type="llm_call") as sp:
            model = kwargs.get("model")
            messages = kwargs.get("messages")
            if model is not None or messages is not None:
                sp.set_io(input={"model": model, "messages": messages})
            response = original(self, *args, **kwargs)
            sp.set_io(output={"response_type": response.__class__.__name__})
            usage = getattr(response, "usage", None)
            choices = getattr(response, "choices", None) or []
            message = getattr(choices[0], "message", None) if choices else None
            content = getattr(message, "content", None)
            # shortcut: provider is fixed even with a custom base_url (OpenRouter); pass cost via set_llm there.
            sp.set_llm(
                provider="openai",
                model=getattr(response, "model", None) or model,
                messages_in=messages,
                messages_out=[{"role": "assistant", "content": content}] if content else None,
                tokens_in=getattr(usage, "prompt_tokens", None),
                tokens_out=getattr(usage, "completion_tokens", None),
            )
            return response

    setattr(wrapped, "__evalops_patched__", True)
    Completions.create = wrapped  # type: ignore[method-assign]
    return True
