"""API key service.

Application rules for project API keys live here so the router only does
parse/auth and returns the response model. Covers list / create / revoke
including the audit-log entries.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.services.audit_service import record_audit
from app.models import ApiKey, Project, utcnow
from app.schemas import ApiKeyCreate, ApiKeyCreateOut, ApiKeyOut
from app.security import generate_api_key, hash_api_key, new_id


def list_keys(db: Session, project: Project) -> list[dict]:
    rows = (
        db.query(ApiKey)
        .filter(ApiKey.project_id == project.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    return [
        ApiKeyOut(
            id=row.id,
            prefix=row.prefix,
            name=row.name,
            environment=row.environment,
            scopes=[s for s in row.scopes.split(",") if s],
            rate_limit_per_minute=row.rate_limit_per_minute,
            created_at=row.created_at,
            revoked_at=row.revoked_at,
            expires_at=row.expires_at,
        ).model_dump()
        for row in rows
    ]


def create_key(
    db: Session,
    project: Project,
    payload: ApiKeyCreate,
    actor_user_id: str,
) -> ApiKeyCreateOut:
    raw_key, prefix = generate_api_key(payload.environment)
    row = ApiKey(
        id=new_id("key"),
        project_id=project.id,
        prefix=prefix,
        hash=hash_api_key(raw_key),
        name=payload.name,
        environment=payload.environment,
        scopes=",".join(payload.scopes),
        rate_limit_per_minute=60,
        expires_at=payload.expires_at,
    )
    db.add(row)
    record_audit(
        db, "api_key.created",
        organization_id=project.organization_id,
        actor_user_id=actor_user_id,
        target_type="api_key",
        target_id=row.id,
        payload={
            "project_id": project.id,
            "key_name": payload.name,
            "environment": payload.environment,
        },
    )
    db.commit()
    db.refresh(row)
    return ApiKeyCreateOut(
        id=row.id,
        prefix=row.prefix,
        name=row.name,
        environment=row.environment,
        scopes=payload.scopes,
        rate_limit_per_minute=row.rate_limit_per_minute,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        expires_at=row.expires_at,
        key=raw_key,
    )


def revoke_key(
    db: Session,
    project: Project,
    key_id: str,
    actor_user_id: str,
) -> ApiKey | None:
    """Idempotent revoke. Returns the row if it belongs to ``project``,
    None when the row is missing or belongs to a different project so
    the router can raise 404 without leaking existence."""
    key = db.get(ApiKey, key_id)
    if not key or key.project_id != project.id:
        return None
    if key.revoked_at is None:
        key.revoked_at = utcnow()
        db.add(key)
        record_audit(
            db, "api_key.revoked",
            organization_id=project.organization_id,
            actor_user_id=actor_user_id,
            target_type="api_key",
            target_id=key.id,
            payload={"project_id": project.id, "key_name": key.name},
        )
        db.commit()
    return key


class ApiKeyStillActiveError(Exception):
    """Raised when caller tries to hard-delete a key that has not been revoked."""


def delete_key(
    db: Session,
    project: Project,
    key_id: str,
    actor_user_id: str,
) -> ApiKey | None:
    """Hard-delete a revoked API key.

    Returns the deleted row, ``None`` when the row is missing or belongs to a
    different project (router translates to 404 without leaking existence), and
    raises :class:`ApiKeyStillActiveError` when the key is still active so the
    router can return 409 — active keys must be revoked first.
    """
    key = db.get(ApiKey, key_id)
    if not key or key.project_id != project.id:
        return None
    if key.revoked_at is None:
        raise ApiKeyStillActiveError(key_id)
    record_audit(
        db, "api_key.deleted",
        organization_id=project.organization_id,
        actor_user_id=actor_user_id,
        target_type="api_key",
        target_id=key.id,
        payload={"project_id": project.id, "key_name": key.name},
    )
    db.delete(key)
    db.commit()
    return key
