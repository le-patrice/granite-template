"""
Authentication controller providing JWT bearer token issuance and revocation.

Adheres strictly to RFC 6749 OAuth2 Password Flow and JSON payload login.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from litestar import Controller, post
from litestar.connection import Request
from litestar.di import Provide
from litestar.exceptions import NotAuthorizedException
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.postgres.user_repository import PostgresUserRepository
from app.core.security import (
    create_access_token,
    decode_access_token,
    revoke_token,
    verify_password_async,
)
from app.core.settings import settings
from app.domain.users.contracts import IUserRepository
from app.domain.users.schemas import TokenResponse
from app.presentation.guards.auth_guard import JWTAuthGuard


async def provide_user_repo(db_session: AsyncSession) -> IUserRepository:
    return PostgresUserRepository(session=db_session)


class AuthController(Controller):
    path = "/auth"
    dependencies: ClassVar[dict[str, Provide]] = {"user_repo": Provide(provide_user_repo)}

    @post(
        path=["/login", "/token"],
        status_code=HTTP_201_CREATED,
        summary="Obtain bearer token",
        description="Exchange email/username + password for a signed JWT bearer token. Supports JSON & OAuth2 form.",
    )
    async def login(
        self,
        request: Request,
        user_repo: IUserRepository,
    ) -> TokenResponse:
        content_type = request.content_type[0] if request.content_type else ""
        if (
            "application/x-www-form-urlencoded" in content_type
            or "multipart/form-data" in content_type
        ):
            form = await request.form()
            email_or_user = form.get("username") or form.get("email") or ""
            password = form.get("password") or ""
        else:
            try:
                body = await request.json()
                email_or_user = body.get("email") or body.get("username") or ""
                password = body.get("password") or ""
            except Exception:  # noqa: BLE001
                raise NotAuthorizedException("Invalid login credentials format.")

        if not email_or_user or not password:
            raise NotAuthorizedException("Incorrect email or password.")

        user = await user_repo.get_by_email(str(email_or_user))
        if not user or not await verify_password_async(str(password), user.hashed_password):
            raise NotAuthorizedException("Incorrect email or password.")

        if not user.is_active:
            raise NotAuthorizedException("User account is inactive.")

        token = create_access_token(subject=str(user.id), is_superuser=user.is_superuser)
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @post(
        path="/logout",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Revoke bearer token",
        description="Revoke the calling bearer token and invalidate in cache store.",
    )
    async def logout(self, request: Request) -> dict[str, str]:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header.removeprefix("Bearer ").strip()
            claims = decode_access_token(token)
            if claims and "jti" in claims:
                exp = claims.get("exp", 0)
                now = datetime.now(UTC).timestamp()
                remaining = (
                    max(1, int(exp - now)) if exp else settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
                )
                await revoke_token(claims["jti"], expires_in=remaining)
        return {"detail": "Token successfully revoked."}
