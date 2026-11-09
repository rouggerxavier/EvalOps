"""Runtime configuration sourced from environment variables.

Lazy getters so tests can mutate ``os.environ`` between calls without
re-importing the module.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_SPANS_PER_TRACE = 500


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def max_body_bytes() -> int:
    return _positive_int("EVALOPS_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES)


def max_spans_per_trace() -> int:
    return _positive_int("EVALOPS_MAX_SPANS_PER_TRACE", DEFAULT_MAX_SPANS_PER_TRACE)


def exports_dir() -> Path:
    """Return an absolute, guaranteed-to-exist directory for export files (G-10).

    Override with EVALOPS_EXPORTS_DIR to decouple from the uvicorn CWD.
    Default resolves relative to this module's location so it never depends
    on where the process was launched from.
    """
    raw = os.environ.get("EVALOPS_EXPORTS_DIR", "")
    if raw and raw.strip():
        p = Path(raw.strip())
    else:
        # apps/api/app/config.py → parent = apps/api/app → parent = apps/api
        p = Path(__file__).parent.parent / "storage" / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def redis_url() -> str | None:
    raw = os.environ.get("REDIS_URL", "").strip()
    return raw or None


def rate_limit_backend() -> str:
    raw = os.environ.get("EVALOPS_RATE_LIMIT_BACKEND", "auto").strip().lower()
    return raw if raw in ("memory", "redis", "auto") else "auto"


def redis_timeout_ms() -> int:
    return _positive_int("EVALOPS_REDIS_TIMEOUT_MS", 200)


def worker_concurrency() -> int:
    return _positive_int("EVALOPS_WORKER_CONCURRENCY", 4)


@dataclass(frozen=True, repr=False)
class RecoveryMailConfig:
    host: str
    port: int
    sender: str
    username: str
    password: str
    tls: str
    timeout: int
    public_origin: str


def recovery_mail_config() -> RecoveryMailConfig | None:
    """Incomplete/unsafe configuration disables public recovery uniformly."""
    from urllib.parse import urlsplit

    host = os.environ.get("EVALOPS_SMTP_HOST", "").strip()
    sender = os.environ.get("EVALOPS_SMTP_FROM", "").strip()
    origin = os.environ.get("EVALOPS_PUBLIC_ORIGIN", "").strip()
    tls = os.environ.get("EVALOPS_SMTP_TLS", "starttls").strip().lower()
    username = os.environ.get("EVALOPS_SMTP_USERNAME", "")
    password = os.environ.get("EVALOPS_SMTP_PASSWORD", "")
    try:
        parsed = urlsplit(origin)
        port = int(os.environ.get("EVALOPS_SMTP_PORT", "587"))
        # Accessing port rejects malformed authorities as well.
        parsed.port
    except (ValueError, TypeError):
        return None
    production = os.environ.get("APP_ENV", "local").lower() not in {"local", "dev", "development", "test"}
    if (not host or not sender or "@" not in sender or any(c in host + sender for c in "\r\n")
            or not redis_url() or tls not in {"starttls", "implicit"} or not 1 <= port <= 65535
            or bool(username) != bool(password) or parsed.scheme not in {"http", "https"}
            or not parsed.hostname or parsed.username is not None or parsed.password is not None
            or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
            or any(c.isspace() for c in origin) or "\\" in origin
            or (production and parsed.scheme != "https")):
        return None
    return RecoveryMailConfig(host, port, sender, username, password, tls,
                              _positive_int("EVALOPS_SMTP_TIMEOUT_SECONDS", 10), origin.rstrip("/"))


def invitations_enabled() -> bool:
    return os.environ.get("EVALOPS_INVITATIONS_ENABLED", "false").strip().lower() in {"1", "true", "yes"}
