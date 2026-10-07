"""
CSRF and Origin Verification Middleware.

Defends against Cross-Site Request Forgery (CSRF) for cookie-authenticated sessions.
Standard API requests using Authorization: Bearer tokens are inherently safe from CSRF
because browsers never attach custom Authorization headers on cross-site form submissions
or embedded script triggers.
"""

from __future__ import annotations

import json
from urllib.parse import urlparse

from litestar.middleware import AbstractMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from app.core.settings import settings


class CSRFOriginMiddleware(AbstractMiddleware):
    """
    Validates Origin / Referer / Sec-Fetch-Site on state-changing HTTP requests
    authenticated via cookies to prevent CSRF exploits.
    """

    SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "GET").upper()
        if method in self.SAFE_METHODS or not settings.CSRF_PROTECTION_ENABLED:
            await self.app(scope, receive, send)
            return

        # Extract headers map
        headers = {
            k.decode("latin1").lower(): v.decode("latin1").strip()
            for k, v in scope.get("headers", [])
        }
        cookie_header = headers.get("cookie", "")

        # CSRF defense is strictly required when session authentication is powered by cookies
        if "access_token" not in cookie_header:
            await self.app(scope, receive, send)
            return

        # 1. Sec-Fetch-Site check (Modern browser defense-in-depth)
        sec_fetch_site = headers.get("sec-fetch-site", "").lower()
        if sec_fetch_site == "cross-site":
            await self._reject(
                send,
                "CSRF verification failed: cross-site state-changing request blocked.",
            )
            return

        # 2. Origin / Referer verification
        origin = headers.get("origin", "")
        referer = headers.get("referer", "")
        source_url = origin or referer

        # Reject cookie-authenticated mutations missing both Origin and Referer
        if not source_url:
            await self._reject(
                send,
                "CSRF verification failed: missing Origin and Referer on cookie-authenticated request.",
            )
            return

        parsed = urlparse(source_url)
        source_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/").lower()

        scheme = scope.get("scheme", "http")
        host = headers.get("host", "").lower()

        allowed = {o.rstrip("/").lower() for o in settings.ALLOWED_ORIGINS}
        if settings.APP_BASE_URL:
            app_parsed = urlparse(settings.APP_BASE_URL)
            allowed.add(f"{app_parsed.scheme}://{app_parsed.netloc}".rstrip("/").lower())

        # Dynamic same-origin host check
        if host:
            allowed.add(f"{scheme}://{host}".rstrip("/").lower())
            allowed.add(f"http://{host}".rstrip("/").lower())
            allowed.add(f"https://{host}".rstrip("/").lower())

        # Built-in test harnesses
        allowed.update(
            {
                "http://testserver",
                "https://testserver",
                "http://testserver.local",
                "https://testserver.local",
            }
        )

        if source_origin not in allowed:
            await self._reject(
                send,
                f"CSRF verification failed: untrusted origin '{source_origin}' for cookie-authenticated request.",
            )
            return

        await self.app(scope, receive, send)

    async def _reject(self, send: Send, message: str) -> None:
        body = json.dumps({"detail": message, "status_code": 403}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            }
        )
