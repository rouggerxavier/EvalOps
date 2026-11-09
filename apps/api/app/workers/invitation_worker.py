"""At-most-once invitation mail. ARQ receives an immutable ID, never a token."""
import asyncio
import logging
import secrets
from datetime import datetime, timezone
from email.headerregistry import Address
from email.message import EmailMessage

from fastapi import HTTPException
from sqlalchemy import update

from app.config import RecoveryMailConfig, invitations_enabled, recovery_mail_config
from app.domain.services.membership_service import organization_lock
from app.domain.services.password_recovery import token_digest
from app.infra.mail import send_message
from app.maintenance.cleanup import _is_expired
from app.models import Membership, OrganizationInvitation

logger = logging.getLogger("evalops.worker.invitation")


def send_invitation_email(config: RecoveryMailConfig, recipient: str, token: str) -> None:
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = Address(addr_spec=recipient)
    message["Subject"] = "Convite para uma organização no EvalOps Studio"
    message.set_content("Você recebeu um convite. Entre na sua conta e confirme o aceite pelo link abaixo. "
                        "O convite expira em 24 horas após a emissão.\n\n"
                        + config.public_origin + "/accept-invitation#" + token)
    send_message(config, message, recipient)


def _dispatch(factory, invitation_id: str, mailer) -> None:
    config = recovery_mail_config()
    if not invitations_enabled() or config is None:
        return
    try:
        with factory() as db:
            org_id = db.query(OrganizationInvitation.organization_id).filter_by(id=invitation_id).scalar()
            if org_id is None:
                return
            with organization_lock(db, org_id):
                invitation = db.query(OrganizationInvitation).filter_by(id=invitation_id).one()
                issuer = db.get(Membership, (invitation.invited_by_user_id, org_id)) if invitation.invited_by_user_id else None
                if (invitation.status != "pending" or _is_expired(invitation.expires_at, datetime.now(timezone.utc))
                        or issuer is None or issuer.role != "owner"):
                    return
                token = secrets.token_urlsafe(32)
                digest = token_digest(token)
                claimed = db.execute(update(OrganizationInvitation).where(
                    OrganizationInvitation.id == invitation_id, OrganizationInvitation.status == "pending",
                ).values(status="sending", token_hash=digest))
                if claimed.rowcount != 1:
                    db.rollback()
                    return
                recipient = invitation.email
                # shortcut: a crash after claim can lose delivery; add an outbox only if guaranteed delivery is required.
                db.commit()
        try:
            mailer(config, recipient, token)
            status = "sent"
        except Exception:
            status = "failed"
            logger.warning("invitation.smtp_failed", extra={"invitation_id": invitation_id})
        with factory() as db:
            with organization_lock(db, org_id):
                db.execute(update(OrganizationInvitation).where(
                    OrganizationInvitation.id == invitation_id, OrganizationInvitation.status == "sending",
                    OrganizationInvitation.token_hash == digest,
                ).values(status=status, token_hash=None if status == "failed" else digest))
                db.commit()
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        # Contention leaves the claim untouched; another explicit request can reissue.
        logger.info("invitation.membership_conflict", extra={"invitation_id": invitation_id})


async def send_invitation_job(ctx: dict, invitation_id: str) -> None:
    await asyncio.to_thread(_dispatch, ctx["db_session_factory"], invitation_id,
                            ctx.get("invitation_mailer", send_invitation_email))
