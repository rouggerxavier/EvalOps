"""Shared SMTP transport; callers own content and recipient validation."""
import smtplib
import ssl
from email.message import EmailMessage

from app.config import RecoveryMailConfig


def send_message(config: RecoveryMailConfig, message: EmailMessage, recipient: str) -> None:
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
