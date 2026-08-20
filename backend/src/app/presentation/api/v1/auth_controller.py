"""
Authentication controller.

POST /api/v1/auth/login   – OAuth2 & JSON password exchange → JWT bearer token
POST /api/v1/auth/token   – OAuth2 standard alias
POST /api/v1/auth/logout  – invalidate current session token (JWT required)
"""
from datetime import datetime, timezone

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
    dependencies = {"user_repo": Provide(provide_user_repo)}

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
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            email_or_user = form.get("username") or form.get("email") or ""
            password = form.get("password") or ""
        else:
            try:
                body = await request.json()
                email_or_user = body.get("email") or body.get("username") or ""
                password = body.get("password") or ""
            except Exception:
                raise NotAuthorizedException("Invalid login credentials format.")

        if not email_or_user or not password:
            raise NotAuthorizedException("Incorrect email or password.")

        user = await user_repo.get_by_email(str(email_or_user))
        if not user or not await verify_password_async(str(password), user.hashed_password):
            raise NotAuthorizedException("Incorrect email or password.")

        token = create_access_token(
            subject=str(user.id),
            is_superuser=bool(user.is_superuser),
        )
        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    @post(
        path="/logout",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Revoke current session",
        description=(
            "Adds the current token's JTI to the Valkey revocation blocklist. "
            "Subsequent requests with the same token will be rejected with 401."
        ),
    )
    async def logout(self, request: Request) -> dict:
        jti: str = request.scope.get("token_jti", "")
        auth_header = request.headers.get("Authorization", "")
        token = auth_header[len("Bearer "):]
        try:
            payload = decode_access_token(token)
            exp = payload.get("exp", 0)
            remaining = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
        except Exception:
            remaining = 3600  # fallback: 1 h

        if jti:
            await revoke_token(jti, expires_in=remaining)

        return {"detail": "Session revoked successfully."}
