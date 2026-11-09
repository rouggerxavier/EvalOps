"""Password recovery persistence. Every mutation locks User before the request row."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.maintenance.cleanup import _is_expired
from app.models import PasswordReset, User
from app.security import hash_password

RESET_TTL = timedelta(minutes=30)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def prepare_request(db: Session, user_id: str, request_id: str, now: datetime) -> int:
    user = db.query(User).filter_by(id=user_id).populate_existing().with_for_update().one()
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    db.add(PasswordReset(user_id=user.id, request_id=request_id, credential_version=user.credential_version,
                         status="pending", token_hash=None, requested_at=now, created_at=now, expires_at=now + RESET_TTL))
    db.commit()
    return user.credential_version


def consume_reset(db: Session, token: str, new_password: str, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    digest = token_digest(token)
    user_id = db.query(PasswordReset.user_id).filter_by(token_hash=digest).scalar()
    if user_id is None:
        return False
    user = db.query(User).filter_by(id=user_id).populate_existing().with_for_update().one_or_none()
    reset = db.query(PasswordReset).filter_by(user_id=user_id).populate_existing().one_or_none()
    if (user is None or reset is None or reset.token_hash != digest
            or reset.status not in {"sending", "sent"} or _is_expired(reset.expires_at, now)
            or reset.credential_version != user.credential_version or not user.password_hash):
        return False
    previous = user.credential_version
    # Version predicate also protects the SQLite development path, where FOR UPDATE is ignored.
    changed = db.execute(update(User).where(User.id == user_id, User.credential_version == previous).values(
        password_hash=hash_password(new_password), credential_version=previous + 1))
    if changed.rowcount != 1:
        db.rollback()
        return False
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == user_id))
    db.commit()
    return True
