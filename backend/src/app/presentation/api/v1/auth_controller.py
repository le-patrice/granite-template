"""
Authentication controller.

POST /api/v1/auth/login   – password exchange → JWT bearer token
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
from app.domain.users.contracts import IUserRepository
from app.domain.users.schemas import LoginRequest, TokenResponse
from app.presentation.guards.auth_guard import JWTAuthGuard


async def provide_user_repo(db_session: AsyncSession) -> IUserRepository:
    return PostgresUserRepository(session=db_session)


class AuthController(Controller):
    path = "/auth"
    dependencies = {"user_repo": Provide(provide_user_repo)}

    @post(
        path="/login",
        status_code=HTTP_201_CREATED,
        summary="Obtain bearer token",
        description="Exchange email + password for a signed JWT bearer token.",
    )
    async def login(
        self,
        data: LoginRequest,
        user_repo: IUserRepository,
    ) -> TokenResponse:
        user = await user_repo.get_by_email(data.email)
        # verify_password_async runs Argon2 in an executor so the event loop
        # is never blocked during the CPU-intensive KDF.
        if not user or not await verify_password_async(data.password, user.hashed_password):
            raise NotAuthorizedException("Incorrect email or password.")

        token = create_access_token(subject=str(user.id))
        return TokenResponse(access_token=token)

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
        # Calculate remaining TTL from the JWT exp claim so the blocklist
        # entry auto-expires when the token would have expired anyway.
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
