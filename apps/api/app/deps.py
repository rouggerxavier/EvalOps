from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.domain.services.rate_limit_service import check_api_key_rate_limit
from app.models import ApiKey, Membership, Project, RevokedToken, User
from app.request_id import set_request_org, set_request_user
from app.security import decode_access_token, verify_api_key


def _is_expired(expires_at: datetime | None, now: datetime) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        now = now.replace(tzinfo=None)
    return expires_at <= now


def get_current_user(
    request: Request,
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

    jti = claims.get("jti")
    if jti and db.get(RevokedToken, jti) is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")
    request.state.user_id = user.id
    set_request_user(user.id)
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
    request: Request,
    x_evalops_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Project:
    return authenticate_api_key(request, x_evalops_key, db, "ingest")


def authenticate_api_key(request: Request, x_evalops_key: str | None, db: Session, scope: str) -> Project:
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

    if _is_expired(selected.expires_at, datetime.now(timezone.utc)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    scopes = {s for s in selected.scopes.split(",") if s}
    if scope not in scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    retry_after = check_api_key_rate_limit(selected.id, selected.rate_limit_per_minute)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too_many_requests",
            headers={"Retry-After": str(retry_after)},
        )

    selected.last_used_at = datetime.now(timezone.utc)
    db.add(selected)
    db.commit()
    project = db.get(Project, selected.project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    request.state.org_id = project.organization_id
    set_request_org(project.organization_id)
    return project
