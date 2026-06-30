"""
Email delivery service for verification, password reset, and invite flows.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import (
    ENABLE_EMAIL_DELIVERY,
    APP_BASE_URL,
    SMTP_FROM_EMAIL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USERNAME,
    SMTP_USE_SSL,
    SMTP_USE_TLS,
    email_runtime_config_summary,
)
from .exceptions import EmailSendError
from .logger import get_logger

logger = get_logger(__name__)


def _send_email(to_email: str, subject: str, body_text: str) -> None:
    """
    Send a plain-text email using configured SMTP settings.
    """
    logger.info(
        "_send_email() entered for recipient=%s subject=%s config=%s",
        to_email,
        subject,
        email_runtime_config_summary(),
    )
    if not ENABLE_EMAIL_DELIVERY:
        logger.info(
            "Email delivery disabled. Subject='%s' recipient='%s'.",
            subject,
            to_email,
        )
        return

    if not SMTP_HOST or not SMTP_FROM_EMAIL:
        logger.error(
            "SMTP configuration missing while email delivery is enabled. config=%s",
            email_runtime_config_summary(),
        )
        raise EmailSendError("Email delivery is enabled but SMTP is not configured")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM_EMAIL
    msg["To"] = to_email
    msg.set_content(body_text)

    try:
        if SMTP_USE_SSL:
            logger.info(
                "SMTP connection opening with SSL host=%s port=%s recipient=%s",
                SMTP_HOST,
                SMTP_PORT,
                to_email,
            )
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                logger.info("SMTP SSL connection opened for recipient=%s", to_email)
                if SMTP_USERNAME:
                    logger.info("SMTP login attempted for recipient=%s username_present=True", to_email)
                    server.login(SMTP_USERNAME, SMTP_PASSWORD or "")
                    logger.info("SMTP login successful for recipient=%s", to_email)
                else:
                    logger.info("SMTP login skipped for recipient=%s username_present=False", to_email)
                logger.info("send_message() called for recipient=%s", to_email)
                server.send_message(msg)
                logger.info("Email sent successfully to %s", to_email)
        else:
            logger.info(
                "SMTP connection opening host=%s port=%s recipient=%s",
                SMTP_HOST,
                SMTP_PORT,
                to_email,
            )
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                logger.info("SMTP connection opened for recipient=%s", to_email)
                if SMTP_USE_TLS:
                    logger.info("TLS start attempted for recipient=%s", to_email)
                    server.starttls()
                    logger.info("TLS started for recipient=%s", to_email)
                else:
                    logger.info("TLS skipped for recipient=%s SMTP_USE_TLS=False", to_email)
                if SMTP_USERNAME:
                    logger.info("SMTP login attempted for recipient=%s username_present=True", to_email)
                    server.login(SMTP_USERNAME, SMTP_PASSWORD or "")
                    logger.info("SMTP login successful for recipient=%s", to_email)
                else:
                    logger.info("SMTP login skipped for recipient=%s username_present=False", to_email)
                logger.info("send_message() called for recipient=%s", to_email)
                server.send_message(msg)
                logger.info("Email sent successfully to %s", to_email)
    except Exception as exc:
        logger.exception(
            "SMTP email send failed for recipient=%s subject=%s config=%s",
            to_email,
            subject,
            email_runtime_config_summary(),
        )
        raise EmailSendError("Failed to send email", original_error=exc) from exc


def build_verify_link(token: str) -> str:
    return f"{APP_BASE_URL}/ui/verify-email?token={token}"


def build_reset_link(token: str) -> str:
    return f"{APP_BASE_URL}/ui/reset-password?token={token}"


def send_email_verification_email(email: str, token: str) -> None:
    logger.info("Preparing email verification message for %s", email)
    link = build_verify_link(token)
    subject = "Verify your email - Placement Portal"
    body = (
        "Welcome to Placement Portal.\n\n"
        "Please verify your email by opening this link:\n"
        f"{link}\n\n"
        "If the link does not open, paste the token below in the Verify Email page:\n"
        f"{token}\n"
    )
    _send_email(email, subject, body)
    logger.info("Email verification sent to %s", email)


def send_password_reset_email(email: str, token: str) -> None:
    logger.info("Preparing password reset message for %s", email)
    link = build_reset_link(token)
    subject = "Reset your password - Placement Portal"
    body = (
        "We received a password reset request.\n\n"
        "Reset your password using this link:\n"
        f"{link}\n\n"
        "If the link does not open, paste the token below in the Reset Password page:\n"
        f"{token}\n"
    )
    _send_email(email, subject, body)
    logger.info("Password reset email sent to %s", email)


def send_student_invite_email(email: str, token: str) -> None:
    logger.info("Preparing student invite message for %s", email)
    link = build_reset_link(token)
    subject = "Your Placement Portal account invite"
    body = (
        "Your admin created a student account for you.\n\n"
        "Set your initial password using this link:\n"
        f"{link}\n\n"
        "If needed, use this token in the Reset Password page:\n"
        f"{token}\n"
    )
    _send_email(email, subject, body)
    logger.info("Student invite email sent to %s", email)
