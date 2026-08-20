"""
Authentication guards — production-hardened.

Guards
------
JWTAuthGuard
    •  Extracts the Bearer token from the Authorization header.
    •  Decodes and validates signature + expiry (via ``decode_access_token``).
    •  Checks the ``jti`` claim against the Valkey revocation blocklist.
    •  Injects ``user_id`` and ``is_superuser`` into ``connection.scope``.

SuperuserGuard
    •  Inherits JWTAuthGuard validation.
    •  Additionally asserts ``is_superuser=True``; raises 403 for standard users.

Usage::

    # Protect a single handler:
    @get("/admin/stats", guards=[SuperuserGuard()])
    async def admin_stats(...): ...

    # Protect an entire controller (applied to all handlers):
    class AdminController(Controller):
        guards = [SuperuserGuard()]
"""
from __future__ import annotations

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.types import RouteHandlerType

from app.core.security import decode_access_token, is_token_revoked


# ---------------------------------------------------------------------------
# JWTAuthGuard
# ---------------------------------------------------------------------------

class JWTAuthGuard:
    """
    Bearer-token guard with Valkey-backed revocation check.

    On success, the following keys are written into ``connection.scope``:
    •  ``user_id``      – str UUID of the authenticated user
    •  ``token_jti``    – str JWT ID (useful for logout handlers)
    •  ``is_superuser`` – bool, defaults to False if claim absent
    """

    async def __call__(
        self,
        connection: ASGIConnection,
        handler: RouteHandlerType,
    ) -> None:
        # ── 1. Extract Authorization header ─────────────────────────────────
        auth_header = connection.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise NotAuthorizedException(
                "Authorization header missing or malformed. "
                "Expected: 'Authorization: Bearer <token>'"
            )

        token = auth_header[len("Bearer "):]

        # ── 2. Decode & validate JWT (signature + expiry) ───────────────────
        try:
            payload = decode_access_token(token)
        except Exception:
            raise NotAuthorizedException("Invalid or expired session token.")

        user_id: str | None = payload.get("sub")
        jti: str | None     = payload.get("jti")

        if not user_id:
            raise NotAuthorizedException("Token is missing 'sub' claim.")

        # ── 3. Revocation check via Valkey ───────────────────────────────────
        if jti and await is_token_revoked(jti):
            raise NotAuthorizedException(
                "This session has been revoked. Please log in again."
            )

        # ── 4. Inject identity into scope ────────────────────────────────────
        connection.scope["user_id"]     = user_id
        connection.scope["token_jti"]   = jti or ""
        connection.scope["is_superuser"] = bool(payload.get("is_superuser", False))


# ---------------------------------------------------------------------------
# SuperuserGuard
# ---------------------------------------------------------------------------

class SuperuserGuard:
    """
    Guard that permits only active superusers.

    Runs the full JWT validation first (via delegation to JWTAuthGuard), then
    asserts the ``is_superuser`` scope flag.  Raises 403 for authenticated
    standard users, 401 for unauthenticated requests.
    """

    def __init__(self) -> None:
        self._auth = JWTAuthGuard()

    async def __call__(
        self,
        connection: ASGIConnection,
        handler: RouteHandlerType,
    ) -> None:
        # Run the full JWT + revocation check first
        await self._auth(connection, handler)

        if not connection.scope.get("is_superuser"):
            raise PermissionDeniedException(
                "This endpoint requires superuser privileges."
            )
