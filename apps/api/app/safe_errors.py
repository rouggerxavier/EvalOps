"""A-12: separate internal exception detail from public API responses.

Public surfaces — HTTP ``detail``, persisted ``error``/``run_metadata``
columns that clients can read back, and the ingest ``errors[]`` array —
must never carry SQL, ORM/driver internals, Python tracebacks,
filesystem paths, tokens/JWT/API keys, cookies or other secrets.

Callers wrap an exception with :func:`safe_message`. A short, vetted,
leak-free string (e.g. a validation message like
``ended_at must be >= started_at``) passes through unchanged so the
client still gets actionable feedback; anything dangerous or unbounded
collapses to a stable slug fallback. The original exception is logged
at WARNING for operators so internal detail is preserved off-band.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("evalops.errors")

#: Stable, opaque slug returned when no safe message can be derived.
GENERIC_ERROR = "internal_error"

#: Upper bound on a pass-through public message. Anything longer is
#: almost certainly a dump (traceback / repr / ORM error) — collapse it.
_MAX_LEN = 200

# If any pattern matches the candidate string, it is treated as leaking
# internals and the public message collapses to the fallback slug.
_LEAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"traceback \(most recent call last\)", re.I),
    re.compile(r"\bsqlalchemy\b", re.I),
    re.compile(r"sqlite3?\b", re.I),
    re.compile(r"psycopg2?", re.I),
    re.compile(r"\bpostgres", re.I),
    re.compile(r"\bIntegrityError\b|\bOperationalError\b|\bProgrammingError\b"),
    re.compile(
        r"\b(no such table|database is locked|constraint failed|unique constraint failed|foreign key constraint failed)\b",
        re.I,
    ),
    re.compile(r"\b(relation|column|table)\s+['\"]?[\w.]+['\"]?\s+does not exist\b", re.I),
    re.compile(r"\b(select|insert|update|delete)\b.{1,80}\b(from|into|set|where|values)\b", re.I | re.S),
    re.compile(r'file "[^"]+\.py"', re.I),
    re.compile(r"line \d+, in ", re.I),
    re.compile(r"(?:^|[\s'\"(=])(?:/(?:home|users|var|tmp|etc|root|opt|mnt)/|[A-Za-z]:\\)", re.I),
    re.compile(r"\.venv[\\/]", re.I),
    re.compile(r" object at 0x[0-9a-fA-F]+", re.I),
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),  # JWT
    re.compile(r"\bevk_[A-Za-z0-9_]{4,}", re.I),  # EvalOps API key
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),  # provider API key
    re.compile(r"\bbearer\s+\S{6,}", re.I),
    re.compile(r"\bset-cookie\b", re.I),
    re.compile(
        r"(?i)\b(password|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization)\b\s*[=:]\s*\S"
    ),
)


def is_safe_public_text(text: str) -> bool:
    """True if ``text`` is short and free of any known leak pattern."""
    if not text:
        return False
    if len(text) > _MAX_LEN:
        return False
    return not any(p.search(text) for p in _LEAK_PATTERNS)


def safe_message(
    exc: BaseException | str,
    *,
    fallback: str = GENERIC_ERROR,
    context: str = "",
) -> str:
    """Return a public-safe string for ``exc``.

    ``exc`` may be an exception or a pre-built message string. A vetted,
    short, leak-free value passes through; anything else becomes
    ``fallback``. The full exception is logged at WARNING (with
    traceback) so operators keep the internal detail.
    """
    raw = exc if isinstance(exc, str) else str(exc)
    if not isinstance(exc, str):
        logger.warning(
            "handled exception%s",
            f" [{context}]" if context else "",
            exc_info=exc,
        )
    if is_safe_public_text(raw):
        return raw
    if context:
        logger.info("error message scrubbed for %s -> %s", context, fallback)
    return fallback
