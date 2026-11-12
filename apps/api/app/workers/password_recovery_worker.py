"""At-most-once recovery dispatch; no raw token enters ARQ, logs or job results."""
from __future__ import annotations

import asyncio
import logging
import secrets
import smtplib
import ssl
from datetime import datetime, timezone
from email.headerregistry import Address
from email.message import EmailMessage

from sqlalchemy import update

from app.config import RecoveryMailConfig, recovery_mail_config
from app.domain.services.password_recovery import RESET_TTL, token_digest
from app.maintenance.cleanup import _is_expired
from app.models import PasswordReset, User

logger = logging.getLogger("evalops.worker.recovery")


def send_reset_email(config: RecoveryMailConfig, recipient: str, token: str) -> None:
    message = EmailMessage()
    message["From"] = config.sender
    message["To"] = Address(addr_spec=recipient)
    message["Subject"] = "Redefinir sua senha do EvalOps Studio"
    message.set_content("Para redefinir sua senha, abra o link abaixo. Ele expira em 30 minutos.\n\n"
                        + config.public_origin + "/reset-password#" + token
                        + "\n\nSe você não pediu esta alteração, ignore este email.")
    context = ssl.create_default_context()
    if config.tls == "implicit":
        connection = smtplib.SMTP_SSL(config.host, config.port, timeout=config.timeout, context=context)
    else:
        connection = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
    with connection as smtp:
        if config.tls == "starttls":
            smtp.starttls(context=context)
        if config.username:
            smtp.login(config.username, config.password)
        smtp.send_message(message, to_addrs=[recipient])


def _dispatch(factory, user_id: str, version: int, request_id: str, requested_at: str, mailer) -> None:
    config = recovery_mail_config()
    if config is None:
        return
    now = datetime.now(timezone.utc)
    with factory() as db:
        user = db.query(User).filter_by(id=user_id).populate_existing().with_for_update().one_or_none()
        reset = db.query(PasswordReset).filter_by(user_id=user_id).populate_existing().one_or_none()
        if (user is None or reset is None or not user.password_hash or user.credential_version != version
                or reset.credential_version != version or reset.request_id != request_id or reset.status != "pending"
                or (reset.requested_at.replace(tzinfo=timezone.utc) if reset.requested_at.tzinfo is None
                    else reset.requested_at.astimezone(timezone.utc)).isoformat() != requested_at
                or _is_expired(reset.expires_at, now)):
            return
        token = secrets.token_urlsafe(32)
        digest = token_digest(token)
        claimed = db.execute(update(PasswordReset).where(
            PasswordReset.user_id == user_id, PasswordReset.request_id == request_id,
            PasswordReset.credential_version == version, PasswordReset.status == "pending",
        ).values(token_hash=digest, status="sending", created_at=now, expires_at=now + RESET_TTL))
        if claimed.rowcount != 1:
            db.rollback()
            return
        recipient = user.email
        # shortcut: this claim prevents retries but a crash can lose mail; add an outbox if delivery must be guaranteed.
        db.commit()
    try:
        mailer(config, recipient, token)
        status = "sent"
    except Exception:
        status = "failed"
        logger.warning("recovery.smtp_failed", extra={"user_id": user_id, "recovery_id": request_id})
    with factory() as db:
        # A later request/password change must survive failure/completion of this SMTP attempt.
        user = db.query(User).filter_by(id=user_id).with_for_update().one_or_none()
        if user is not None:
            db.execute(update(PasswordReset).where(PasswordReset.user_id == user_id,
                       PasswordReset.request_id == request_id, PasswordReset.token_hash == digest).values(
                           status=status, token_hash=None if status == "failed" else digest))
            db.commit()


async def send_password_reset_job(ctx: dict, user_id: str, version: int, request_id: str, requested_at: str) -> None:
    await asyncio.to_thread(_dispatch, ctx["db_session_factory"], user_id, version, request_id, requested_at,
                            ctx.get("recovery_mailer", send_reset_email))
