"""PII redaction service for trace ingestion (G-08 / A-13).

Redaction is opt-in: activated by ``tags.pii=true`` on the trace payload
or by the ``X-EvalOps-Redact`` request header.  When active, every span
/ trace / event field that may carry raw user content is cleared before
persistence.

A-13 scope expansion — redaction previously only cleared span
``messages_in/out`` and ``input/output``.  It now also clears the other
PII-bearing surfaces identified in the audit: span ``error`` and
``metadata``, trace ``tags`` / ``user_ref`` / ``metadata``, and event
``payload``.  Cleared dict columns keep their container type (``{}``)
and nullable columns become ``None`` so the row stays debuggable and
``Trace.redacted=True`` records *why* the content is empty.  Redaction
never runs unless opt-in is active (no automatic DLP).
"""
from __future__ import annotations

from typing import Any


def should_redact(tags: dict | None, redact_header: str | None) -> bool:
    """Return True if this trace should be redacted."""
    if tags:
        pii_val = tags.get("pii")
        if pii_val is True or str(pii_val).lower() == "true":
            return True
    return redact_header is not None


def redact_span(span: Any) -> None:
    """Clear every PII-bearing field on a persisted ``Span`` row.

    Nullable JSON columns drop to ``None``; the non-nullable
    ``metadata`` dict drops to ``{}`` so the column type is preserved.
    ``tools`` (tool *definitions*, not user content) is intentionally
    left intact.
    """
    span.messages_in = None
    span.messages_out = None
    span.input = None
    span.output = None
    span.error = None
    span.metadata_json = {}


def redact_event(event: Any) -> None:
    """Clear an ``Event`` payload (free-form, may carry PII)."""
    event.payload = {}


def redact_trace(trace: Any) -> None:
    """Clear trace-level PII surfaces.

    ``should_redact`` is evaluated from the inbound payload tags *before*
    this runs, so dropping ``tags`` here cannot affect the opt-in
    decision.
    """
    trace.tags = {}
    trace.user_ref = None
    trace.metadata_json = {}
