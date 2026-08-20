"""
Asynchronous transactional email dispatcher.

Architecture
------------
•  ``MailService`` is the single public interface.  It is transport-agnostic:
   - When SMTP credentials are configured (``settings.smtp_configured``) it
     sends via aiosmtplib (async SMTP).
   - When credentials are absent (dev / test) it falls back to *mock mode*:
     the full email body is rendered and emitted via structlog at INFO level
     so developers can see exactly what would be sent without needing a mail
     server.

•  Token generation helpers (``generate_reset_token``, ``generate_verify_token``)
   produce signed JWTs; the ``RESET_TOKEN_EXPIRE_MINUTES`` and
   ``VERIFY_TOKEN_EXPIRE_MINUTES`` settings control their lifetimes.

•  Background dispatch: ``send_in_background(msg)`` enqueues a coroutine via
   ``asyncio.create_task()`` so the HTTP response is never blocked by SMTP
   latency.  Callers that need delivery guarantees should use a task queue
   (SAQ / Celery); this helper is intentionally lightweight.

•  Template rendering uses the dead-simple ``{{PLACEHOLDER}}`` substitution
   already adopted in our HTML templates — no Jinja2 dep required.

Template placeholders consumed
-------------------------------
password_reset.html / .txt:
    APP_NAME, USER_NAME, RESET_URL, EXPIRES_HOURS

account_verification.html / .txt:
    APP_NAME, USER_NAME, VERIFY_URL, EXPIRES_HOURS

Dependencies (add to pyproject.toml when enabling real SMTP):
    aiosmtplib>=3.0.0     – async SMTP client

Reference: references/litestar-fullstack/src/py/app/lib/email/service.py
           references/fastapi-template/backend/app/utils.py
"""

from __future__ import annotations

import asyncio
import re
import smtplib
from dataclasses import dataclass
from datetime import timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import structlog

from app.core.security import create_signed_token
from app.core.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Template engine (lightweight, no Jinja2 required)
# ---------------------------------------------------------------------------

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_HTML_TAG_RE = re.compile(r"<[^<]+?>")
_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def _load_template(name: str) -> str:
    path = _TEMPLATE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"Email template not found: {path}")
    return path.read_text(encoding="utf-8")


def _render(template_name: str, context: dict[str, str | int]) -> str:
    """Substitute {{PLACEHOLDER}} tokens in a template string."""
    source = _load_template(template_name)
    full_context = {"APP_NAME": settings.APP_NAME, **context}

    def replacer(m: re.Match) -> str:
        return str(full_context.get(m.group(1), m.group(0)))

    return _PLACEHOLDER_RE.sub(replacer, source)


def _html_to_text(html: str) -> str:
    """Strip HTML tags and normalise whitespace for the plain-text part."""
    text = _HTML_TAG_RE.sub("", html)
    for entity, char in (
        ("&nbsp;", " "),
        ("&amp;", "&"),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&quot;", '"'),
    ):
        text = text.replace(entity, char)
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Email message dataclass
# ---------------------------------------------------------------------------


@dataclass
class EmailMessage:
    to_address: str
    subject: str
    html_body: str
    text_body: str | None = None  # auto-generated from html_body if None
    from_address: str | None = None  # falls back to settings.EMAILS_FROM_ADDRESS
    reply_to: str | None = None

    def __post_init__(self) -> None:
        if self.text_body is None:
            self.text_body = _html_to_text(self.html_body)
        if self.from_address is None:
            self.from_address = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_ADDRESS}>"


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


async def _send_smtp(msg: EmailMessage) -> None:
    """
    Send via aiosmtplib when available; falls back to stdlib smtplib in a
    thread-pool executor so we never block the event loop.

    aiosmtplib is an optional dependency.  If not installed, we use
    asyncio.get_running_loop().run_in_executor with smtplib — synchronous but
    non-blocking from the event loop's perspective.
    """
    mime = MIMEMultipart("alternative")
    mime["Subject"] = msg.subject
    mime["From"] = msg.from_address or settings.EMAILS_FROM_ADDRESS
    mime["To"] = msg.to_address
    if msg.reply_to:
        mime["Reply-To"] = msg.reply_to

    mime.attach(MIMEText(msg.text_body or "", "plain", "utf-8"))
    mime.attach(MIMEText(msg.html_body, "html", "utf-8"))

    try:
        import aiosmtplib  # optional dep

        await aiosmtplib.send(
            mime,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER,
            password=settings.SMTP_PASSWORD,
            start_tls=settings.SMTP_TLS,
        )
    except ImportError:
        # aiosmtplib not installed — run smtplib in executor
        def _sync_send() -> None:
            with smtplib.SMTP(settings.SMTP_HOST or "localhost", settings.SMTP_PORT) as srv:
                if settings.SMTP_TLS:
                    srv.starttls()
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    srv.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                srv.sendmail(mime["From"], [msg.to_address], mime.as_string())

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _sync_send)


async def _send_mock(msg: EmailMessage) -> None:
    """Log the email to structlog instead of sending — used in dev / test."""
    await logger.ainfo(
        "📧  [MOCK MAIL — no SMTP configured]",
        to=msg.to_address,
        subject=msg.subject,
        from_address=msg.from_address,
        text_preview=((msg.text_body or "")[:200] + "…")
        if len(msg.text_body or "") > 200
        else msg.text_body,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


class MailService:
    """
    Async email dispatcher with automatic mock fallback.

    Usage::

        mail = MailService()
        await mail.send_password_reset(user_email="alice@example.com",
                                       user_name="Alice",
                                       reset_token=token)
    """

    async def _dispatch(self, msg: EmailMessage) -> None:
        if settings.smtp_configured:
            await _send_smtp(msg)
        else:
            await _send_mock(msg)

    def send_in_background(self, msg: EmailMessage) -> asyncio.Task:
        """
        Fire-and-forget dispatch.  The returned Task can be awaited if
        delivery confirmation is needed, but callers may safely ignore it.
        """
        return asyncio.create_task(self._dispatch(msg))

    # ── Transactional messages ──────────────────────────────────────────────

    async def send_password_reset(
        self,
        user_email: str,
        user_name: str,
        reset_token: str,
    ) -> None:
        """Render and dispatch a password-reset email."""
        expires_hours = max(1, settings.RESET_TOKEN_EXPIRE_MINUTES // 60)
        reset_url = f"{settings.APP_BASE_URL}/reset-password?token={reset_token}"
        html = _render(
            "password_reset.html",
            {
                "USER_NAME": user_name,
                "RESET_URL": reset_url,
                "EXPIRES_HOURS": expires_hours,
            },
        )
        txt = _render(
            "password_reset.txt",
            {
                "USER_NAME": user_name,
                "RESET_URL": reset_url,
                "EXPIRES_HOURS": expires_hours,
            },
        )
        await self._dispatch(
            EmailMessage(
                to_address=user_email,
                subject=f"Reset your {settings.APP_NAME} password",
                html_body=html,
                text_body=txt,
            )
        )

    async def send_account_verification(
        self,
        user_email: str,
        user_name: str,
        verify_token: str,
    ) -> None:
        """Render and dispatch an account-verification email."""
        expires_hours = max(1, settings.VERIFY_TOKEN_EXPIRE_MINUTES // 60)
        verify_url = f"{settings.APP_BASE_URL}/verify-email?token={verify_token}"
        html = _render(
            "account_verification.html",
            {
                "USER_NAME": user_name,
                "VERIFY_URL": verify_url,
                "EXPIRES_HOURS": expires_hours,
            },
        )
        txt = _render(
            "account_verification.txt",
            {
                "USER_NAME": user_name,
                "VERIFY_URL": verify_url,
                "EXPIRES_HOURS": expires_hours,
            },
        )
        await self._dispatch(
            EmailMessage(
                to_address=user_email,
                subject=f"Verify your {settings.APP_NAME} email address",
                html_body=html,
                text_body=txt,
            )
        )


# ---------------------------------------------------------------------------
# Token helpers (signed JWTs, validated by security.decode_access_token)
# ---------------------------------------------------------------------------


def generate_reset_token(user_email: str) -> str:
    """Return a short-lived password-reset JWT scoped to *user_email*."""
    return create_signed_token(
        subject=user_email,
        scope="password_reset",
        expires_delta=timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES),
    )


def generate_verify_token(user_email: str) -> str:
    """Return a long-lived email-verification JWT scoped to *user_email*."""
    return create_signed_token(
        subject=user_email,
        scope="email_verify",
        expires_delta=timedelta(minutes=settings.VERIFY_TOKEN_EXPIRE_MINUTES),
    )


# Module-level singleton — import and use directly:
#   from app.core.mail import mail_service
mail_service = MailService()
