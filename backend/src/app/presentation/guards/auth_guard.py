"""
Authentication and Role-Based Access Control (RBAC) guards.

Guards
------
1. JWTAuthGuard / jwt_auth_guard
   • Validates Authorization: Bearer <token>
   • Checks Valkey revocation blocklist
   • Populates connection.scope with user_id, tenant_id, role, is_superuser, token_jti

2. SuperuserGuard / SuperAdminGuard / superuser_guard
   • Validates superadmin privileges (is_superuser=True or role='superadmin')
   • Raises 401 if unauthenticated, 403 Forbidden if not superuser
"""

from __future__ import annotations

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

        token = auth_header[len("Bearer ") :]

        # Decode & validate JWT (signature + expiry)
        try:
            payload = decode_access_token(token)
        except Exception:  # noqa: BLE001
            raise NotAuthorizedException("Invalid or expired session token.")

        user_id: str | None = payload.get("sub")
        jti: str | None = payload.get("jti")
        is_super: bool = bool(payload.get("is_superuser", False))
        tenant_id: str | None = payload.get("tenant_id") or payload.get("organization_id")
        role: str = payload.get("role") or ("superadmin" if is_super else "user")

        if not user_id:
            raise NotAuthorizedException("Token is missing 'sub' claim.")

        # Revocation check via Valkey
        if jti and await is_token_revoked(jti):
            raise NotAuthorizedException("This session has been revoked. Please log in again.")

        # Inject identity into scope and connection
        connection.scope["user_id"] = user_id
        connection.scope["token_jti"] = jti or ""
        connection.scope["is_superuser"] = is_super
        connection.scope["tenant_id"] = tenant_id or ""
        connection.scope["role"] = role


jwt_auth_guard = JWTAuthGuard()


def superuser_guard(connection: ASGIConnection, _: RouteHandlerType) -> None:
    """
    Asserts that the current authenticated user has is_superuser=True or role='superadmin'.
    """
    user_id = connection.scope.get("user_id")
    if not user_id:
        raise NotAuthorizedException("Authentication required.")
    is_super = connection.scope.get("is_superuser", False)
    role = connection.scope.get("role", "")
    if not (is_super or role == "superadmin"):
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


# Standardized SuperAdminGuard alias
SuperAdminGuard = SuperuserGuard

__all__ = [
    "JWTAuthGuard",
    "SuperAdminGuard",
    "SuperuserGuard",
    "jwt_auth_guard",
    "superuser_guard",
]
