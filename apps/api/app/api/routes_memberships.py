from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.routes import _decode_cursor, _encode_cursor, _to_utc
from app.config import invitations_enabled, recovery_mail_config
from app.db import get_db
from app.deps import ensure_org_membership, get_current_user
from app.domain.services import membership_service as service
from app.domain.services.rate_limit_service import check_invitation_rate_limit
from app.models import OrganizationInvitation, User
from app.schemas import InvitationAccept, InvitationCreate, InvitationOut, MemberOut, MembershipUpdate, OwnershipTransfer

router = APIRouter(prefix="/v1")


def _invitation_out(invitation: OrganizationInvitation) -> dict:
    result = InvitationOut.model_validate(invitation).model_dump()
    result["status"] = service.effective_status(invitation, datetime.now(timezone.utc))
    return result


@router.post("/organizations/{org_id}/invitations", status_code=202, response_model=InvitationOut)
async def issue_invitation(org_id: str, payload: InvitationCreate, request: Request,
                           user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ensure_org_membership(db, user.id, org_id, "admin")
    if not invitations_enabled() or recovery_mail_config() is None:
        raise HTTPException(status_code=503, detail="invitations_unavailable")
    try:
        pool = request.app.state.arq_pool
        if pool is None:
            raise RuntimeError("queue_unavailable")
        await pool.ping()
        retry = check_invitation_rate_limit(org_id, user.id)
    except Exception:
        raise HTTPException(status_code=503, detail="invitations_unavailable") from None
    if retry is not None:
        raise HTTPException(status_code=429, detail="too_many_requests", headers={"Retry-After": str(retry)})
    invitation = service.create_invitation(db, org_id, user.id, payload.email, payload.role)
    invitation_id = invitation.id
    try:
        queued = await pool.enqueue_job("send_invitation_job", invitation_id, _job_id=invitation_id,
            _expires=max(0, (_to_utc(invitation.expires_at) - datetime.now(timezone.utc)).total_seconds()))
        if queued is None:
            raise RuntimeError("enqueue_unconfirmed")
    except Exception:
        try:
            advanced = service.compensate_enqueue(db, org_id, invitation_id)
        except Exception:
            advanced = False
        if not advanced:
            raise HTTPException(status_code=503, detail="invitations_unavailable") from None
    db.refresh(invitation)
    return _invitation_out(invitation)


@router.get("/organizations/{org_id}/invitations")
def list_invitations(org_id: str, limit: int = Query(50, ge=1, le=200), cursor: str | None = None,
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    ensure_org_membership(db, user.id, org_id, "admin")
    query = db.query(OrganizationInvitation).filter_by(organization_id=org_id)
    if cursor:
        created_at, invitation_id = _decode_cursor(cursor)
        try:
            created_at = _to_utc(created_at)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="invalid_cursor") from None
        query = query.filter(or_(OrganizationInvitation.created_at > created_at,
            and_(OrganizationInvitation.created_at == created_at, OrganizationInvitation.id > invitation_id)))
    rows = query.order_by(OrganizationInvitation.created_at, OrganizationInvitation.id).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {"data": [_invitation_out(row) for row in rows],
            "next_cursor": _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more else None}


@router.post("/organizations/{org_id}/invitations/{invitation_id}/revoke", status_code=204)
def revoke_invitation(org_id: str, invitation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    service.revoke_invitation(db, org_id, user.id, invitation_id)
    return Response(status_code=204)


@router.post("/invitations/accept")
def accept_invitation(payload: InvitationAccept, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return service.accept_invitation(db, user.id, payload.token)


@router.patch("/organizations/{org_id}/members/{user_id}", response_model=MemberOut)
def update_membership(org_id: str, user_id: str, payload: MembershipUpdate,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MemberOut:
    membership = service.change_membership(db, org_id, user.id, user_id, payload.role)
    target = db.get(User, user_id)
    return MemberOut(user_id=user_id, email=target.email, name=target.name,
                     role=membership.role, joined_at=membership.created_at)


@router.delete("/organizations/{org_id}/members/{user_id}", status_code=204)
def remove_membership(org_id: str, user_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    service.change_membership(db, org_id, user.id, user_id, None)
    return Response(status_code=204)


@router.post("/organizations/{org_id}/ownership/transfer", status_code=204)
def transfer_ownership(org_id: str, payload: OwnershipTransfer,
                       user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Response:
    service.transfer_ownership(db, org_id, user.id, payload.user_id)
    return Response(status_code=204)
