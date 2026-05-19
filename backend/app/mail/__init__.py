"""Email delivery — SMTP-backed in production, no-op in test, logging in dev.

Magic-link emails are the only thing we send in v1. The interface is small
enough that we don't pull in a templating library; raw f-strings + a tiny
HTML body are sufficient.

Backends:
  - test: NullMailer — records the call, does nothing
  - local: LogMailer  — logs the email body so devs can copy/paste
  - prod/demo/staging: SMTPMailer — actually sends through the configured host
"""
from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text_body: str
    html_body: str | None = None
    from_addr: str = "no-reply@atrio.app"


class Mailer(Protocol):
    """Send an email. Raises on transport failure."""

    def send(self, email: Email) -> None: ...


# ----------------------------------------------------- implementations


class NullMailer:
    """Test-only — accumulates sends in a list."""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    def send(self, email: Email) -> None:
        self.sent.append(email)


class LogMailer:
    """Local-dev mailer — prints the email body to the structured log."""

    def send(self, email: Email) -> None:
        log.info(
            "email_sent_to_log",
            to=email.to,
            subject=email.subject,
            body_preview=email.text_body[:200],
        )


@dataclass
class SMTPConfig:
    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    timeout_seconds: float = 10.0


@dataclass
class SMTPMailer:
    """Production mailer — talks SMTP over STARTTLS."""

    config: SMTPConfig
    _send_fn: object = field(default=None, repr=False)  # injected for tests

    def send(self, email: Email) -> None:
        msg = EmailMessage()
        msg["From"] = email.from_addr
        msg["To"] = email.to
        msg["Subject"] = email.subject
        msg.set_content(email.text_body)
        if email.html_body:
            msg.add_alternative(email.html_body, subtype="html")

        if self._send_fn is not None:
            self._send_fn(msg)  # type: ignore[operator]
            return

        log.info("smtp_sending", to=email.to, host=self.config.host)
        with smtplib.SMTP(
            self.config.host, self.config.port, timeout=self.config.timeout_seconds
        ) as s:
            if self.config.use_tls:
                s.starttls()
            if self.config.username:
                s.login(self.config.username, self.config.password)
            s.send_message(msg)


# ----------------------------------------------------- factory + helpers


def build_mailer(settings: Settings | None = None) -> Mailer:
    """Pick the right mailer for the current env."""
    s = settings or get_settings()
    env = s.atrio_env
    if env == "test":
        return NullMailer()
    if env == "local":
        return LogMailer()
    # demo / staging / prod use SMTP — but allow falling back to LogMailer if
    # SMTP_HOST isn't configured (so a partial demo deploy doesn't crash).
    if not s.smtp_host:
        log.warning("smtp_not_configured_using_logmailer", env=env)
        return LogMailer()
    return SMTPMailer(
        config=SMTPConfig(
            host=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_user,
            password=s.smtp_pass,
            use_tls=s.smtp_tls,
        )
    )


def render_magic_link_email(*, email: str, link_url: str, expires_minutes: int = 15) -> Email:
    """Render the magic-link email body. Plain text + HTML."""
    text_body = (
        f"Hello,\n\n"
        f"To sign in to ATRIO Boardroom, click the link below:\n\n"
        f"  {link_url}\n\n"
        f"This link expires in {expires_minutes} minutes.\n"
        f"If you didn't request this, you can safely ignore this email.\n\n"
        f"— ATRIO Boardroom\n"
    )
    html_body = (
        "<!doctype html>"
        "<html><body style=\"font-family: Georgia, serif; max-width: 560px; "
        "margin: 40px auto; color: #171615;\">"
        "<h1 style=\"font-size: 28px; margin: 0 0 16px;\">Sign in to ATRIO</h1>"
        "<p style=\"font-size: 16px; line-height: 1.6;\">Click the button "
        "below to sign in. This link expires in "
        f"{expires_minutes} minutes.</p>"
        f"<p style=\"margin: 32px 0;\"><a href=\"{link_url}\" "
        "style=\"display:inline-block; padding: 12px 24px; background: #171615; "
        "color: #f7f4ee; text-decoration: none; font-family: -apple-system, "
        "sans-serif; font-size: 14px; letter-spacing: 0.05em; "
        "text-transform: uppercase;\">Sign in</a></p>"
        "<p style=\"font-size: 13px; color: #615b53;\">If the button doesn't "
        f"work, paste this URL into your browser:<br><code>{link_url}</code></p>"
        "<hr style=\"border: none; border-top: 1px solid #cfc8bd; margin: 32px 0;\">"
        "<p style=\"font-size: 12px; color: #615b53;\">If you didn't request "
        "this email, you can safely ignore it.</p>"
        "</body></html>"
    )
    return Email(
        to=email,
        subject="Sign in to ATRIO Boardroom",
        text_body=text_body,
        html_body=html_body,
    )
