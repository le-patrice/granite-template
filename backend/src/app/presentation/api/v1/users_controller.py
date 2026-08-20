"""
Users presentation controller.

Endpoints
---------
POST  /api/v1/users/register  – open registration (no auth required)
GET   /api/v1/users/me        – fetch own profile      (JWT required)
PATCH /api/v1/users/me        – update name / password (JWT required)
"""
import uuid

from litestar import Controller, get, patch, post
from litestar.connection import Request
from litestar.di import Provide
from litestar.exceptions import (
    ClientException,
    NotFoundException,
)
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.postgres.user_repository import PostgresUserRepository
from app.core.security import get_password_hash
from app.domain.users.contracts import IUserRepository
from app.domain.users.models import User
from app.domain.users.schemas import UserCreate, UserRead, UserUpdate
from app.presentation.guards.auth_guard import JWTAuthGuard


# ---------------------------------------------------------------------------
# Dependency provider (shared with AuthController)
# ---------------------------------------------------------------------------

async def provide_user_repo(db_session: AsyncSession) -> IUserRepository:
    return PostgresUserRepository(session=db_session)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _model_to_read(user: User) -> UserRead:
    """Convert a User ORM model to the UserRead response schema."""
    return UserRead(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_superuser=user.is_superuser,
    )


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class UsersController(Controller):
    path = "/users"
    dependencies = {"user_repo": Provide(provide_user_repo)}

    # ------------------------------------------------------------------
    # POST /register  — open, no auth required
    # ------------------------------------------------------------------

    @post(
        path="/register",
        status_code=HTTP_201_CREATED,
        summary="Open user registration",
        description="Create a new standard (non-superuser) account. No JWT required.",
    )
    async def register(
        self,
        data: UserCreate,
        user_repo: IUserRepository,
    ) -> UserRead:
        # Conflict check: email must be unique
        existing = await user_repo.get_by_email(data.email)
        if existing:
            raise ClientException(
                detail="An account with this email already exists.",
                status_code=409,
            )

        new_user = User(
            email=data.email,
            hashed_password=get_password_hash(data.password),
            full_name=data.full_name,
            is_active=True,
            is_superuser=False,
        )
        created = await user_repo.create(new_user)
        return _model_to_read(created)

    # ------------------------------------------------------------------
    # GET /me  — JWT required
    # ------------------------------------------------------------------

    @get(
        path="/me",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Get own profile",
        description="Returns the profile of the currently authenticated user.",
    )
    async def get_me(
        self,
        request: Request,
        user_repo: IUserRepository,
    ) -> UserRead:
        raw_id: str = request.scope["user_id"]
        user = await user_repo.get_by_id(uuid.UUID(raw_id))
        if user is None:
            raise NotFoundException(detail="User not found.")
        return _model_to_read(user)

    # ------------------------------------------------------------------
    # PATCH /me  — JWT required
    # ------------------------------------------------------------------

    @patch(
        path="/me",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Update own profile",
        description="Update the authenticated user's full_name and/or password.",
    )
    async def update_me(
        self,
        request: Request,
        data: UserUpdate,
        user_repo: IUserRepository,
    ) -> UserRead:
        raw_id: str = request.scope["user_id"]
        user = await user_repo.get_by_id(uuid.UUID(raw_id))
        if user is None:
            raise NotFoundException(detail="User not found.")

        # Apply only the fields that were explicitly supplied
        if data.full_name is not None:
            user.full_name = data.full_name

        if data.password is not None:
            user.hashed_password = get_password_hash(data.password)

        updated = await user_repo.update(user)
        return _model_to_read(updated)
