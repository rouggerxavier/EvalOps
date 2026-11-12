"""Organization-first serialization for invitation and membership mutations."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.deps import ensure_org_membership
from app.domain.services.audit_service import record_audit
from app.domain.services.password_recovery import token_digest
from app.maintenance.cleanup import _is_expired
from app.models import Membership, Organization, OrganizationInvitation, User
from app.security import new_id

INVITATION_TTL = timedelta(hours=24)
OPEN_STATUSES = ("pending", "sending", "sent")


@contextmanager
def organization_lock(db: Session, org_id: str):
    try:
        query = db.query(Organization).filter_by(id=org_id).populate_existing()
        if db.get_bind().dialect.name == "sqlite":
            org = query.one_or_none()
            if org is not None:
                version = org.membership_version
                claimed = db.execute(update(Organization).where(
                    Organization.id == org_id, Organization.membership_version == version,
                ).values(membership_version=version + 1), execution_options={"synchronize_session": False})
                if claimed.rowcount != 1:
                    raise HTTPException(status_code=409, detail="membership_conflict")
                org = query.one()
        else:
            org = query.with_for_update(nowait=True).one_or_none()
        if org is None:
            raise HTTPException(status_code=404, detail="not_found")
        # Previously loaded memberships/users must never authorize a mutation.
        db.expire_all()
        yield org
    except OperationalError as exc:
        db.rollback()
        code = getattr(exc.orig, "sqlstate", None)
        sqlite_code = getattr(exc.orig, "sqlite_errorcode", None)
        if (db.get_bind().dialect.name == "postgresql" and code == "55P03") or (
            db.get_bind().dialect.name == "sqlite" and sqlite_code is not None
            and sqlite_code & 0xFF in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}
        ):
            raise HTTPException(status_code=409, detail="membership_conflict") from None
        raise
    except Exception:
        db.rollback()
        raise


@contextmanager
def owner_lock(db: Session, org_id: str, actor_id: str):
    # Forbidden requests cannot reach SQLite's write/CAS or external effects.
    ensure_org_membership(db, actor_id, org_id, "admin")
    with organization_lock(db, org_id) as org:
        ensure_org_membership(db, actor_id, org_id, "admin")
        yield org


def effective_status(invitation: OrganizationInvitation, now: datetime) -> str:
    if invitation.status in OPEN_STATUSES and _is_expired(invitation.expires_at, now):
        return "expired"
    return invitation.status


def revoke_email(db: Session, org_id: str, email: str, now: datetime) -> None:
    db.execute(update(OrganizationInvitation).where(
        OrganizationInvitation.organization_id == org_id, OrganizationInvitation.email == email,
        OrganizationInvitation.status.in_(OPEN_STATUSES),
    ).values(status="revoked", revoked_at=now, token_hash=None))


def create_invitation(db: Session, org_id: str, actor_id: str, email: str, role: str) -> OrganizationInvitation:
    with owner_lock(db, org_id, actor_id):
        if db.query(Membership).join(User).filter(
            Membership.organization_id == org_id, User.email == email,
        ).first() is not None:
            raise HTTPException(status_code=409, detail="already_member")
        now = datetime.now(timezone.utc)
        revoke_email(db, org_id, email, now)
        invitation = OrganizationInvitation(id=new_id("inv"), organization_id=org_id, email=email, role=role,
            invited_by_user_id=actor_id, status="pending", created_at=now, expires_at=now + INVITATION_TTL)
        db.add(invitation)
        record_audit(db, "invitation.created", organization_id=org_id, actor_user_id=actor_id,
                     target_type="invitation", target_id=invitation.id)
        db.commit()
        return invitation


def compensate_enqueue(db: Session, org_id: str, invitation_id: str) -> bool:
    with organization_lock(db, org_id):
        invitation = db.query(OrganizationInvitation).filter_by(id=invitation_id, organization_id=org_id).one()
        advanced = invitation.status in {"sending", "sent", "accepted", "revoked"}
        db.execute(update(OrganizationInvitation).where(
            OrganizationInvitation.id == invitation_id, OrganizationInvitation.status == "pending",
        ).values(status="failed", token_hash=None))
        db.commit()
        return advanced


def accept_invitation(db: Session, actor_id: str, token: str) -> dict:
    invalid = HTTPException(status_code=400, detail="invalid_invitation")
    digest = token_digest(token)
    org_id = db.query(OrganizationInvitation.organization_id).filter_by(token_hash=digest).scalar()
    if org_id is None:
        raise invalid
    with organization_lock(db, org_id) as org:
        invitation = db.query(OrganizationInvitation).filter_by(token_hash=digest, organization_id=org_id).one_or_none()
        user = db.query(User).filter_by(id=actor_id).populate_existing().one_or_none()
        now = datetime.now(timezone.utc)
        if (invitation is None or invitation.status not in {"sending", "sent"}
                or _is_expired(invitation.expires_at, now) or user is None or user.email != invitation.email):
            raise invalid
        issuer = db.get(Membership, (invitation.invited_by_user_id, org_id)) if invitation.invited_by_user_id else None
        if issuer is None or issuer.role != "owner":
            raise invalid
        membership = db.get(Membership, (actor_id, org_id))
        already_member = membership is not None
        if membership is None:
            membership = Membership(user_id=actor_id, organization_id=org_id, role=invitation.role)
            db.add(membership)
        invitation.status, invitation.token_hash, invitation.accepted_at = "accepted", None, now
        record_audit(db, "invitation.accepted", organization_id=org_id, actor_user_id=actor_id,
                     target_type="invitation", target_id=invitation.id)
        from app.deps import ROLE_PERMISSIONS
        result = {"organization_id": org.id, "organization_slug": org.slug, "role": membership.role,
                  "permissions": sorted(ROLE_PERMISSIONS.get(membership.role, ())), "already_member": already_member}
        db.commit()
        return result


def revoke_invitation(db: Session, org_id: str, actor_id: str, invitation_id: str) -> None:
    with owner_lock(db, org_id, actor_id):
        invitation = db.query(OrganizationInvitation).filter_by(id=invitation_id, organization_id=org_id).one_or_none()
        if invitation is None:
            raise HTTPException(status_code=404, detail="not_found")
        if invitation.status == "accepted":
            raise HTTPException(status_code=409, detail="invitation_already_accepted")
        invitation.token_hash = None
        if invitation.status not in {"revoked", "failed"} and effective_status(invitation, datetime.now(timezone.utc)) != "expired":
            invitation.status, invitation.token_hash = "revoked", None
            invitation.revoked_at = datetime.now(timezone.utc)
            record_audit(db, "invitation.revoked", organization_id=org_id, actor_user_id=actor_id,
                         target_type="invitation", target_id=invitation_id)
        db.commit()


def change_membership(db: Session, org_id: str, actor_id: str, user_id: str, role: str | None) -> Membership | None:
    with owner_lock(db, org_id, actor_id):
        member = db.get(Membership, (user_id, org_id))
        if member is None:
            raise HTTPException(status_code=404, detail="not_found")
        if member.role == "owner" and db.query(Membership).filter(
            Membership.organization_id == org_id, Membership.role == "owner", Membership.user_id != user_id,
        ).count() == 0:
            raise HTTPException(status_code=409, detail="last_owner")
        before = member.role
        if role is None:
            user = db.query(User).filter_by(id=user_id).populate_existing().one()
            revoke_email(db, org_id, user.email, datetime.now(timezone.utc))
            db.delete(member)
        else:
            member.role = role
        record_audit(db, "membership.removed" if role is None else "membership.updated", organization_id=org_id,
                     actor_user_id=actor_id, target_type="membership", target_id=user_id,
                     payload={"from": before, "to": role})
        db.commit()
        return member if role is not None else None


def transfer_ownership(db: Session, org_id: str, actor_id: str, target_id: str) -> None:
    with owner_lock(db, org_id, actor_id):
        target = db.get(Membership, (target_id, org_id))
        if target is None:
            raise HTTPException(status_code=404, detail="not_found")
        if target_id == actor_id or target.role not in {"member", "viewer"}:
            raise HTTPException(status_code=409, detail="invalid_transfer")
        before = target.role
        target.role = "owner"
        actor = db.get(Membership, (actor_id, org_id))
        actor.role = "member"
        record_audit(db, "ownership.transferred", organization_id=org_id, actor_user_id=actor_id,
                     target_type="membership", target_id=target_id,
                     payload={"from": before, "to": "owner", "actor_from": "owner", "actor_to": "member"})
        db.commit()
