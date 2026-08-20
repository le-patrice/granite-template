"""
Authentication and Role-Based Access Control (RBAC) guards.

Guards
------
1. JWTAuthGuard / jwt_auth_guard
   • Validates Authorization: Bearer <token>
   • Checks Valkey revocation blocklist
   • Populates connection.scope with user_id, is_superuser, token_jti

2. superuser_guard / SuperuserGuard
   • Validates superadmin privileges (is_superuser=True)
   • Raises 401 if unauthenticated, 403 Forbidden if not superuser
"""
from __future__ import annotations

from typing import Any

from litestar.connection import ASGIConnection
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from litestar.types import RouteHandlerType

from app.core.security import decode_access_token, is_token_revoked


class JWTAuthGuard:
    """
    Bearer-token guard with Valkey-backed revocation check.
    """

    async def __call__(
        self,
        connection: ASGIConnection,
        handler: RouteHandlerType,
    ) -> None:
        # Extract Authorization header
        auth_header = connection.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise NotAuthorizedException(
                "Authorization header missing or malformed. "
                "Expected: 'Authorization: Bearer <token>'"
            )

        token = auth_header[len("Bearer "):]

        # Decode & validate JWT (signature + expiry)
        try:
            payload = decode_access_token(token)
        except Exception:
            raise NotAuthorizedException("Invalid or expired session token.")

        user_id: str | None = payload.get("sub")
        jti: str | None = payload.get("jti")
        is_super: bool = bool(payload.get("is_superuser", False))

        if not user_id:
            raise NotAuthorizedException("Token is missing 'sub' claim.")

        # Revocation check via Valkey
        if jti and await is_token_revoked(jti):
            raise NotAuthorizedException(
                "This session has been revoked. Please log in again."
            )

        # Inject identity into scope and connection
        connection.scope["user_id"] = user_id
        connection.scope["token_jti"] = jti or ""
        connection.scope["is_superuser"] = is_super


jwt_auth_guard = JWTAuthGuard()


def superuser_guard(connection: ASGIConnection, _: RouteHandlerType) -> None:
    """
    Asserts that the current authenticated user has is_superuser=True.
    """
    user_id = connection.scope.get("user_id")
    if not user_id:
        raise NotAuthorizedException("Authentication required.")
    if not connection.scope.get("is_superuser", False):
        raise PermissionDeniedException("Superadmin privileges required to perform this action.")


class SuperuserGuard:
    """
    Composite guard that verifies JWT authentication and enforces superuser privileges.
    """

    def __init__(self) -> None:
        self._auth = JWTAuthGuard()

    async def __call__(
        self,
        connection: ASGIConnection,
        handler: RouteHandlerType,
    ) -> None:
        await self._auth(connection, handler)
        superuser_guard(connection, handler)
