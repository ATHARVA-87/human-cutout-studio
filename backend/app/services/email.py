"""Sending emails (verification and password-reset links).

Three interchangeable "backends", chosen with SEGMENTATION_EMAIL_BACKEND:
- "console": writes the email to the log and keeps it in `outbox` (tests, and a safe fallback)
- "smtp":    any SMTP server, e.g. the local Mailpit inbox from docker-compose (http://localhost:8025)
- "brevo":   Brevo's HTTPS API, for production. Render's free plan blocks SMTP ports (25/465/587),
             so production email has to go over HTTPS.
Routes call `send_email` through FastAPI BackgroundTasks, so the HTTP response never waits for the
email server, and a failed send is logged instead of breaking the request.
"""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage

from backend.app.core.config import settings

logger = logging.getLogger("human_cutout.email")
BREVO_URL = "https://api.brevo.com/v3/smtp/email"


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str


outbox: list[Email] = []  # what the console backend "sent" (tests read verification links from here)


def send_email(email: Email) -> None:
    try:
        if settings.email_backend == "smtp":
            _send_smtp(email)
        elif settings.email_backend == "brevo":
            _send_brevo(email)
        else:
            outbox.append(email)
            logger.info("email (console backend) to=%s subject=%r\n%s", email.to, email.subject, email.text)
    except Exception:
        logger.exception("sending email failed (subject=%r)", email.subject)  # never log the link itself


def _send_smtp(email: Email) -> None:
    message = EmailMessage()
    message["From"] = f"{settings.email_from_name} <{settings.email_from}>"
    message["To"] = email.to
    message["Subject"] = email.subject
    message.set_content(email.text)
    message.add_alternative(email.html, subtype="html")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
        if settings.smtp_starttls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(message)


def _send_brevo(email: Email) -> None:
    body = {
        "sender": {"name": settings.email_from_name, "email": settings.email_from},
        "to": [{"email": email.to}],
        "subject": email.subject,
        "textContent": email.text,
        "htmlContent": email.html,
    }
    request = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(body).encode(),
        headers={"api-key": settings.brevo_api_key, "content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # raises on HTTP errors
        response.read()


BUTTON_STYLE = (
    "display:inline-block;background:#1d5a43;color:#ffffff;padding:12px 18px;border-radius:6px;text-decoration:none;font-weight:bold"
)
NOTE_STYLE = "color:#55554f;font-size:13px;line-height:1.5"


def _layout(heading: str, paragraph: str, button: str, link: str, footnote: str) -> str:
    """A small, plain HTML email that works in every mail client (inline styles only)."""
    return (
        '<div style="font-family:Arial,sans-serif;max-width:520px;margin:auto;color:#171717">'
        f'<h2 style="margin:0 0 12px">{heading}</h2>'
        f'<p style="line-height:1.5">{paragraph}</p>'
        f'<p><a href="{link}" style="{BUTTON_STYLE}">{button}</a></p>'
        f'<p style="{NOTE_STYLE}">{footnote}<br>If the button doesn\'t work, copy this link into your browser:<br>{link}</p>'
        "</div>"
    )


def verification_email(to: str, link: str) -> Email:
    hours = settings.verify_token_hours
    return Email(
        to=to,
        subject="Confirm your email for Human Cutout",
        text=f"Confirm your email address to start making cutouts:\n\n{link}\n\nThe link works for {hours} hours. "
        "If you didn't create an account, ignore this email.",
        html=_layout(
            "Confirm your email",
            "Confirm your email address to start making cutouts.",
            "Confirm email",
            link,
            f"The link works for {hours} hours. If you didn't create an account, you can ignore this email.",
        ),
    )


def reset_email(to: str, link: str) -> Email:
    minutes = settings.reset_token_minutes
    return Email(
        to=to,
        subject="Reset your Human Cutout password",
        text=f"Someone asked to reset the password for this email address. To choose a new password, open:\n\n{link}\n\n"
        f"The link works for {minutes} minutes and only once. If it wasn't you, ignore this email; your password stays the same.",
        html=_layout(
            "Reset your password",
            "Someone asked to reset the password for this email address. Choose a new password with the button below.",
            "Choose a new password",
            link,
            f"The link works for {minutes} minutes and only once. If it wasn't you, ignore this email; your password stays the same.",
        ),
    )
