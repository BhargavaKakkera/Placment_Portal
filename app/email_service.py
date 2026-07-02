from __future__ import annotations

import smtplib
import json
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import (
    ENABLE_EMAIL_DELIVERY,
    APP_BASE_URL,
    EMAIL_FROM,
    EMAIL_PROVIDER,
    RESEND_API_KEY,
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


def _send_resend_email(to_email: str, subject: str, body_text: str, body_html: str) -> None:
    if not RESEND_API_KEY or not EMAIL_FROM:
        raise EmailSendError("Resend email delivery is enabled but not configured")

    payload = json.dumps(
        {
            "from": EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "text": body_text,
            "html": body_html,
        }
    ).encode("utf-8")
    request = Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "PlacementPortal/1.0",
        },
        method="POST",
    )

    try:
        logger.info("Resend API send called for recipient=%s", to_email)
        with urlopen(request, timeout=15) as response:
            response_body = response.read().decode("utf-8")
        logger.info("Resend API email sent to %s response=%s", to_email, response_body)
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        logger.exception(
            "Resend API email failed for recipient=%s status=%s body=%s",
            to_email,
            exc.code,
            error_body,
        )
        raise EmailSendError("Failed to send email", original_error=exc) from exc
    except URLError as exc:
        logger.exception("Resend API network error for recipient=%s", to_email)
        raise EmailSendError("Failed to send email", original_error=exc) from exc


def _send_smtp_email(to_email: str, subject: str, body_text: str, body_html: str) -> None:
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
    msg.add_alternative(body_html, subtype="html")

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
                logger.info(
                    "SMTP login attempted for recipient=%s username_present=True", to_email
                )
                server.login(SMTP_USERNAME, SMTP_PASSWORD or "")
                logger.info("SMTP login successful for recipient=%s", to_email)
            else:
                logger.info(
                    "SMTP login skipped for recipient=%s username_present=False", to_email
                )
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
                logger.info(
                    "SMTP login attempted for recipient=%s username_present=True", to_email
                )
                server.login(SMTP_USERNAME, SMTP_PASSWORD or "")
                logger.info("SMTP login successful for recipient=%s", to_email)
            else:
                logger.info(
                    "SMTP login skipped for recipient=%s username_present=False", to_email
                )
            logger.info("send_message() called for recipient=%s", to_email)
            server.send_message(msg)
            logger.info("Email sent successfully to %s", to_email)


def _send_email(to_email: str, subject: str, body_text: str, body_html: str) -> None:
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

    try:
        if EMAIL_PROVIDER == "resend":
            _send_resend_email(to_email, subject, body_text, body_html)
        else:
            _send_smtp_email(to_email, subject, body_text, body_html)
    except EmailSendError:
        raise
    except Exception as exc:
        logger.exception(
            "Email send failed for recipient=%s subject=%s config=%s",
            to_email,
            subject,
            email_runtime_config_summary(),
        )
        raise EmailSendError("Failed to send email", original_error=exc) from exc


def build_verify_link(token: str) -> str:
    return f"{APP_BASE_URL}/ui/verify-email?token={token}"


def build_reset_link(token: str) -> str:
    return f"{APP_BASE_URL}/ui/reset-password?token={token}"


def _build_brand_footer() -> tuple[str, str]:
    plain = (
        "\nPlacement Portal\n"
        f"{APP_BASE_URL}\n"
    )
    html = (
        '<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;">'
        '<p style="margin:0;font-size:13px;line-height:1.6;color:#6b7280;">Placement Portal</p>'
        f'<p style="margin:4px 0 0;font-size:13px;line-height:1.6;color:#6b7280;">{APP_BASE_URL}</p>'
        '</div>'
    )
    return plain, html


def _wrap_email_content(
    title: str,
    intro: str,
    action_text: str,
    action_url: str,
    closing: str,
) -> tuple[str, str]:
    footer_plain, footer_html = _build_brand_footer()
    plain = (
        f"Hello,\n\n"
        f"{intro}\n\n"
        f"{action_text}\n\n"
        f"{action_url}\n\n"
        f"{closing}\n"
        f"{footer_plain}"
    )
    html = f"""
<!doctype html>
<html lang=\"en\">
    <body style=\"margin:0;padding:0;background:#f6f8fb;font-family:Arial,Helvetica,sans-serif;color:#111827;\">
        <div style=\"max-width:640px;margin:0 auto;padding:24px;\">
            <div style=\"background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;padding:32px;box-shadow:0 12px 30px rgba(15,23,42,.06);\">
                <div style=\"font-size:14px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:#2563eb;margin-bottom:12px;\">{title}</div>
                <h1 style=\"margin:0 0 16px;font-size:28px;line-height:1.2;color:#0f172a;\">{title}</h1>
                <p style=\"margin:0 0 16px;font-size:16px;line-height:1.7;color:#334155;\">{intro}</p>
                <div style=\"margin:24px 0;padding:18px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:14px;\">
                    <p style=\"margin:0;font-size:15px;line-height:1.7;color:#0f172a;\">{action_text}</p>
                    <p style=\"margin:12px 0 0;font-size:15px;line-height:1.7;color:#2563eb;word-break:break-word;\">{action_url}</p>
                </div>
                <p style=\"margin:0;font-size:15px;line-height:1.7;color:#334155;\">{closing}</p>
                {footer_html}
            </div>
        </div>
    </body>
</html>
""".strip()
    return plain, html


def send_email_verification_email(email: str, token: str) -> None:
    logger.info("Preparing email verification message for %s", email)
    link = build_verify_link(token)

    subject = "Verify your Placement Portal email"

    body, body_html = _wrap_email_content(
        title="Verify your email",
        intro="Thanks for creating your Placement Portal account. Verify your email address to activate the account.",
        action_text="Open the link below to verify your email address:",
        action_url=link,
        closing="If you did not create this account, you can safely ignore this email.",
    )

    _send_email(email, subject, body, body_html)
    logger.info("Email verification sent to %s", email)


def send_password_reset_email(email: str, token: str) -> None:
    logger.info("Preparing password reset message for %s", email)
    link = build_reset_link(token)

    subject = "Reset your Placement Portal password"

    body, body_html = _wrap_email_content(
        title="Reset your password",
        intro="We received a request to reset your Placement Portal password.",
        action_text="Open the link below to choose a new password:",
        action_url=link,
        closing="If you did not request this, you can safely ignore this email.",
    )

    _send_email(email, subject, body, body_html)
    logger.info("Password reset email sent to %s", email)


def send_student_invite_email(email: str, token: str) -> None:
    logger.info("Preparing student invite message for %s", email)
    link = build_reset_link(token)

    subject = "Set up your Placement Portal password"

    body, body_html = _wrap_email_content(
        title="Set up your account",
        intro="Your admin has created a student account for you in Placement Portal.",
        action_text="Open the link below to set your initial password:",
        action_url=link,
        closing="If you were not expecting this message, you can ignore it.",
    )

    _send_email(email, subject, body, body_html)
    logger.info("Student invite email sent to %s", email)

