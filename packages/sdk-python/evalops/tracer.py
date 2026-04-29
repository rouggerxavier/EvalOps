from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
import random
import secrets
from typing import Any, Callable

from evalops.uploader import BackgroundUploader, UploaderConfig


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    return repr(value)


@dataclass
class SpanRecord:
    client_span_id: str
    parent_client_span_id: str | None
    span_type: str
    name: str
    started_at: datetime
    status: str = "ok"
    ended_at: datetime | None = None
    input: dict | None = None
    output: dict | None = None
    metadata: dict = field(default_factory=dict)
    error: dict | None = None

    def finish(self) -> None:
        self.ended_at = _now()

    def to_payload(self) -> dict[str, Any]:
        ended_at = self.ended_at or _now()
        return {
            "client_span_id": self.client_span_id,
            "parent_client_span_id": self.parent_client_span_id,
            "type": self.span_type,
            "name": self.name,
            "started_at": _utc_iso(self.started_at),
            "ended_at": _utc_iso(ended_at),
            "status": self.status,
            "input": _safe(self.input),
            "output": _safe(self.output),
            "metadata": _safe(self.metadata),
            "error": _safe(self.error),
            "events": [],
        }


@dataclass
class TraceRecord:
    client_trace_id: str
    name: str
    started_at: datetime
    service: str | None
    environment: str
    tags: dict
    spans: list[SpanRecord] = field(default_factory=list)
    status: str = "ok"
    error: dict | None = None

    def to_payload(self) -> dict[str, Any]:
        ended_at = _now()
        metadata = {"sdk": {"name": "evalops-python", "version": "0.1.0"}}
        if self.error:
            metadata["error"] = self.error
        return {
            "client_trace_id": self.client_trace_id,
            "name": self.name,
            "service": self.service,
            "environment": self.environment,
            "started_at": _utc_iso(self.started_at),
            "ended_at": _utc_iso(ended_at),
            "status": self.status,
            "tags": _safe(self.tags),
            "metadata": metadata,
            "spans": [span.to_payload() for span in self.spans],
        }


class SpanHandle:
    def __init__(self, record: SpanRecord) -> None:
        self._record = record

    def set_io(self, *, input: dict | None = None, output: dict | None = None) -> None:
        if input is not None:
            self._record.input = input
        if output is not None:
            self._record.output = output

    def set_error(self, *, message: str, type: str = "error") -> None:
        self._record.status = "error"
        self._record.error = {"type": type, "message": message}


class EvalOpsTracer:
    def __init__(self) -> None:
        self._uploader: BackgroundUploader | None = None
        self._disabled = True
        self._project = ""
        self._environment = "dev"
        self._service: str | None = None
        self._tags: dict = {}
        self._sample_rate = 1.0
        self._trace_ctx: ContextVar[TraceRecord | None] = ContextVar("trace_ctx", default=None)
        self._span_stack: ContextVar[list[str]] = ContextVar("span_stack", default=[])

    def init(
        self,
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
        self._project = project
        self._environment = environment
        self._service = service or project
        self._tags = tags or {}
        self._sample_rate = sample_rate
        self._disabled = disabled
        if self._disabled:
            return
        self._uploader = BackgroundUploader(UploaderConfig(api_url=api_url.rstrip("/"), api_key=api_key))

    def trace(self, name: str) -> Callable:
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                if self._disabled or random.random() > self._sample_rate:
                    return func(*args, **kwargs)
                if self._trace_ctx.get() is not None:
                    return func(*args, **kwargs)

                record = TraceRecord(
                    client_trace_id=f"ct_{secrets.token_hex(8)}",
                    name=name,
                    started_at=_now(),
                    service=self._service,
                    environment=self._environment,
                    tags=self._tags,
                )
                token_trace = self._trace_ctx.set(record)
                token_stack = self._span_stack.set([])
                try:
                    with self.span(name=name, type="chain") as root:
                        root.set_io(input={"args": _safe(list(args)), "kwargs": _safe(kwargs)})
                        result = func(*args, **kwargs)
                        root.set_io(output={"result": _safe(result)})
                    return result
                except Exception as exc:  # noqa: BLE001
                    record.status = "error"
                    record.error = {"type": exc.__class__.__name__, "message": str(exc)}
                    raise
                finally:
                    self._trace_ctx.reset(token_trace)
                    self._span_stack.reset(token_stack)
                    if self._uploader is not None:
                        self._uploader.submit(record.to_payload())

            return wrapper

        return decorator

    @contextmanager
    def span(self, name: str, type: str = "chain") -> Any:
        trace = self._trace_ctx.get()
        if self._disabled or trace is None:
            yield SpanHandle(
                SpanRecord(
                    client_span_id="noop",
                    parent_client_span_id=None,
                    span_type=type,
                    name=name,
                    started_at=_now(),
                )
            )
            return

        stack = list(self._span_stack.get())
        parent = stack[-1] if stack else None
        span_id = f"cs_{secrets.token_hex(6)}"
        record = SpanRecord(
            client_span_id=span_id,
            parent_client_span_id=parent,
            span_type=type,
            name=name,
            started_at=_now(),
        )
        trace.spans.append(record)
        stack.append(span_id)
        token_stack = self._span_stack.set(stack)
        handle = SpanHandle(record)
        try:
            yield handle
        except Exception as exc:  # noqa: BLE001
            handle.set_error(message=str(exc), type=exc.__class__.__name__)
            raise
        finally:
            record.finish()
            new_stack = list(self._span_stack.get())
            if new_stack:
                new_stack.pop()
            self._span_stack.reset(token_stack)
            self._span_stack.set(new_stack)

    def flush(self) -> None:
        if self._uploader is not None:
            self._uploader.flush()
