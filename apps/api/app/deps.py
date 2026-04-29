from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ApiKey, Membership, Project, User
from app.security import decode_access_token, verify_api_key


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        claims = decode_access_token(token)
        user_id = claims["sub"]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized") from exc

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    return user


def ensure_org_membership(db: Session, user_id: str, org_id: str) -> Membership:
    membership = (
        db.query(Membership)
        .filter(Membership.user_id == user_id, Membership.organization_id == org_id)
        .one_or_none()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return membership


def get_project_from_api_key(
    x_evalops_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Project:
    if not x_evalops_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    key_prefix = x_evalops_key[:14]
    candidates = db.query(ApiKey).filter(ApiKey.prefix == key_prefix, ApiKey.revoked_at.is_(None)).all()
    selected: ApiKey | None = None
    for candidate in candidates:
        if verify_api_key(x_evalops_key, candidate.hash):
            selected = candidate
            break
    if selected is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    scopes = {s for s in selected.scopes.split(",") if s}
    if "ingest" not in scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    selected.last_used_at = datetime.now(timezone.utc)
    db.add(selected)
    db.commit()
    project = db.get(Project, selected.project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return project
