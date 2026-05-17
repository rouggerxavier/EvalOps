"""request context helpers for request_id and structured logging.

Allowed charset: alphanumeric, hyphen, underscore, dot — max 128 chars.
Rejects newlines, control chars, and anything outside the safe set.
"""
from __future__ import annotations

from contextvars import ContextVar, Token
import re
import secrets

_SAFE_RE = re.compile(r'^[a-zA-Z0-9\-_.]{1,128}$')

_request_id_var: ContextVar[str | None] = ContextVar("evalops_request_id", default=None)
_user_id_var: ContextVar[str | None] = ContextVar("evalops_user_id", default=None)
_org_id_var: ContextVar[str | None] = ContextVar("evalops_org_id", default=None)

RequestContextTokens = tuple[Token[str | None], Token[str | None], Token[str | None]]


def sanitize_request_id(value: str | None) -> str:
    """Return a safe request ID: reuse value if valid, else generate fresh."""
    if value and _SAFE_RE.match(value):
        return value
    return secrets.token_urlsafe(16)


def set_request_context(
    *,
    request_id: str,
    user_id: str | None = None,
    org_id: str | None = None,
) -> RequestContextTokens:
    return (
        _request_id_var.set(request_id),
        _user_id_var.set(user_id),
        _org_id_var.set(org_id),
    )


def reset_request_context(tokens: RequestContextTokens) -> None:
    request_id_token, user_id_token, org_id_token = tokens
    _org_id_var.reset(org_id_token)
    _user_id_var.reset(user_id_token)
    _request_id_var.reset(request_id_token)


def set_request_user(user_id: str | None) -> None:
    _user_id_var.set(user_id)


def set_request_org(org_id: str | None) -> None:
    _org_id_var.set(org_id)


def get_request_id() -> str | None:
    return _request_id_var.get()


def get_user_id() -> str | None:
    return _user_id_var.get()


def get_org_id() -> str | None:
    return _org_id_var.get()
