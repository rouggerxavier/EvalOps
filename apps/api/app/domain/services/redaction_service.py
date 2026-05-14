"""PII redaction service for trace ingestion (G-08).

Redaction is opt-in: activated by tags.pii=true on the trace payload
or by the X-EvalOps-Redact request header.  When active, span fields
that may carry raw user content are cleared before persistence.
"""
from __future__ import annotations


def should_redact(tags: dict | None, redact_header: str | None) -> bool:
    """Return True if this trace should be redacted."""
    if tags:
        pii_val = tags.get("pii")
        if pii_val is True or str(pii_val).lower() == "true":
            return True
    return redact_header is not None
