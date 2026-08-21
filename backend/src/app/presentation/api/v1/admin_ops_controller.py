"""
Admin and system operations controller ported from reference utils.py.

Endpoints:
• POST /api/v1/utils/test-email/   – Test email transmission (Superadmin only)
• GET  /api/v1/utils/health-check/ – Basic health ping
"""

from __future__ import annotations

from typing import Annotated, Any

from litestar import Controller, get, post
from litestar.params import Body, Parameter
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED

from app.core.mail import send_test_email
from app.domain.users.schemas import Message
from app.presentation.guards.auth_guard import SuperuserGuard


class AdminOpsController(Controller):
    path = "/utils"

    @post(
        path="/test-email/",
        guards=[SuperuserGuard()],
        status_code=HTTP_201_CREATED,
        summary="Test email delivery",
        description="Dispatch a test transaction email to verify SMTP configuration.",
    )
    async def test_email(
        self,
        email_to: Annotated[str | None, Parameter(query="email_to", required=False)] = None,
        data: Annotated[dict[str, Any] | None, Body(default=None)] = None,
    ) -> Message:
        target = (
            email_to
            or (data.get("email_to") if isinstance(data, dict) else None)
            or "tester@example.com"
        )
        await send_test_email(email_to=target)
        return Message(message="Test email sent")

    @get(
        path="/health-check/",
        status_code=HTTP_200_OK,
        summary="Basic health check",
        description="Lightweight ping endpoint.",
    )
    async def health_check(self) -> bool:
        return True
