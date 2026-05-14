"""Centralized audit logging helper (G-06).

Wraps AuditLog creation so a failure never crashes the calling operation.
Add entries within the same DB session/transaction as the main operation so
they commit atomically; the try/except only guards against malformed payloads
or session edge cases.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.security import new_id

logger = logging.getLogger(__name__)


def record_audit(
    db: Session,
    action: str,
    *,
    organization_id: str | None = None,
    actor_user_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    payload: dict | None = None,
) -> None:
    try:
        db.add(
            AuditLog(
                id=new_id("adt"),
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                payload=payload or {},
            )
        )
    except Exception:
        logger.exception("audit log failed for action=%s target_id=%s", action, target_id)
