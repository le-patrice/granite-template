"""
Users presentation controller with strict Role-Based Access Control (RBAC).

Ported 1:1 from reference implementation with async database repository.

Endpoints
---------
Public:
  • POST  /api/v1/users/register        – Open self-registration
  • POST  /api/v1/users/signup          – Signup alias

Self Profile (JWT Required):
  • GET   /api/v1/users/me              – Fetch own user profile
  • PATCH /api/v1/users/me              – Update own profile (name, email)
  • PATCH /api/v1/users/me/password     – Update own password
  • DELETE /api/v1/users/me             – Delete own account

Superadmin Management (SuperuserGuard Required):
  • POST   /api/v1/users/               – Provision new user
  • GET    /api/v1/users/               – List all registered users (paginated + count)
  • GET    /api/v1/users/{user_id}      – Retrieve single user details
  • PATCH  /api/v1/users/{user_id}      – Update user profile, roles, or active status
  • PATCH  /api/v1/users/{user_id}/role – Assign/modify user privileges & roles
  • DELETE /api/v1/users/{user_id}      – Delete user account
"""

from __future__ import annotations

import uuid
from typing import ClassVar

from litestar import Controller, delete, get, patch, post
from litestar.connection import Request
from litestar.di import Provide
from litestar.exceptions import ClientException, NotFoundException
from litestar.status_codes import HTTP_200_OK, HTTP_201_CREATED
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.postgres.user_repository import PostgresUserRepository
from app.core.security import get_password_hash, verify_password_async
from app.domain.users.contracts import IUserRepository
from app.domain.users.models import User
from app.domain.users.schemas import (
    Message,
    UpdatePassword,
    UserAdminCreate,
    UserAdminUpdate,
    UserCreate,
    UserRead,
    UsersPublic,
    UserUpdateMe,
)
from app.presentation.guards.auth_guard import JWTAuthGuard, SuperuserGuard

# ---------------------------------------------------------------------------
# Dependency provider
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
    dependencies: ClassVar[dict[str, Provide]] = {"user_repo": Provide(provide_user_repo)}

    # ------------------------------------------------------------------
    # POST /register & /signup — open self-registration
    # ------------------------------------------------------------------

    @post(
        path=["/register", "/signup"],
        status_code=HTTP_201_CREATED,
        summary="Open user registration",
        description="Create a new standard (non-superuser) account. No JWT required.",
    )
    async def register(
        self,
        data: UserCreate,
        user_repo: IUserRepository,
    ) -> UserRead:
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
    # GET /me — JWT required
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
        raw_id: str = request.scope.get("user_id", "")
        if not raw_id:
            raise NotFoundException(detail="User not found.")
        user = await user_repo.get_by_id(uuid.UUID(raw_id))
        if user is None:
            raise NotFoundException(detail="User not found.")
        return _model_to_read(user)

    # ------------------------------------------------------------------
    # PATCH /me — JWT required
    # ------------------------------------------------------------------

    @patch(
        path="/me",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Update own profile",
        description="Update the authenticated user's full_name and/or email.",
    )
    async def update_me(
        self,
        request: Request,
        data: UserUpdateMe,
        user_repo: IUserRepository,
    ) -> UserRead:
        raw_id: str = request.scope.get("user_id", "")
        if not raw_id:
            raise NotFoundException(detail="User not found.")
        current_id = uuid.UUID(raw_id)
        user = await user_repo.get_by_id(current_id)
        if user is None:
            raise NotFoundException(detail="User not found.")

        if data.email and data.email != user.email:
            existing = await user_repo.get_by_email(data.email)
            if existing and existing.id != current_id:
                raise ClientException(detail="User with this email already exists", status_code=409)
            user.email = data.email

        if data.full_name is not None:
            user.full_name = data.full_name

        if data.password is not None:
            user.hashed_password = get_password_hash(data.password)

        updated = await user_repo.update(user)
        return _model_to_read(updated)

    # ------------------------------------------------------------------
    # PATCH /me/password — JWT required
    # ------------------------------------------------------------------

    @patch(
        path="/me/password",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Update own password",
        description="Validate current password and set a new password.",
    )
    async def update_password_me(
        self,
        request: Request,
        data: UpdatePassword,
        user_repo: IUserRepository,
    ) -> Message:
        raw_id: str = request.scope.get("user_id", "")
        if not raw_id:
            raise NotFoundException(detail="User not found.")
        user = await user_repo.get_by_id(uuid.UUID(raw_id))
        if user is None:
            raise NotFoundException(detail="User not found.")

        verified = await verify_password_async(data.current_password, user.hashed_password)
        if not verified:
            raise ClientException(detail="Incorrect password", status_code=400)
        if data.current_password == data.new_password:
            raise ClientException(
                detail="New password cannot be the same as the current one",
                status_code=400,
            )

        user.hashed_password = get_password_hash(data.new_password)
        await user_repo.update(user)
        return Message(message="Password updated successfully")

    # ------------------------------------------------------------------
    # DELETE /me — JWT required
    # ------------------------------------------------------------------

    @delete(
        path="/me",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Delete own user",
        description="Delete current user account. Superusers cannot delete themselves.",
    )
    async def delete_me(
        self,
        request: Request,
        user_repo: IUserRepository,
    ) -> Message:
        raw_id: str = request.scope.get("user_id", "")
        if not raw_id:
            raise NotFoundException(detail="User not found.")
        current_id = uuid.UUID(raw_id)
        user = await user_repo.get_by_id(current_id)
        if user is None:
            raise NotFoundException(detail="User not found.")
        if user.is_superuser:
            raise ClientException(
                detail="Super users are not allowed to delete themselves",
                status_code=403,
            )

        await user_repo.delete(current_id)
        return Message(message="User deleted successfully")

    # ------------------------------------------------------------------
    # POST / — Superadmin only: Provision new user with roles
    # ------------------------------------------------------------------

    @post(
        path=["", "/"],
        guards=[SuperuserGuard()],
        status_code=HTTP_201_CREATED,
        summary="Provision user (Admin)",
        description="Superadmin endpoint to create a user with custom roles and superuser status.",
    )
    async def create_user_admin(
        self,
        data: UserAdminCreate,
        user_repo: IUserRepository,
    ) -> UserRead:
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
            is_active=data.is_active,
            is_superuser=data.is_superuser,
        )
        created = await user_repo.create(new_user)
        return _model_to_read(created)

    # ------------------------------------------------------------------
    # GET / — Superadmin only: List all users (paginated + count)
    # ------------------------------------------------------------------

    @get(
        path=["", "/"],
        guards=[SuperuserGuard()],
        status_code=HTTP_200_OK,
        summary="List users (Admin)",
        description="Superadmin endpoint to list all platform user records.",
    )
    async def list_users(
        self,
        user_repo: IUserRepository,
        skip: int = 0,
        limit: int = 100,
    ) -> UsersPublic:
        users = await user_repo.list_all(limit=limit, offset=skip)
        count = await user_repo.count_all()
        return UsersPublic(data=[_model_to_read(u) for u in users], count=count)

    # ------------------------------------------------------------------
    # GET /{user_id} — User details
    # ------------------------------------------------------------------

    @get(
        path="/{user_id:uuid}",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Get user details (Admin)",
        description="Retrieve details of a user by UUID.",
    )
    async def get_user_by_id(
        self,
        user_id: uuid.UUID,
        request: Request,
        user_repo: IUserRepository,
    ) -> UserRead:
        raw_id: str = request.scope.get("user_id", "")
        is_superuser: bool = bool(request.scope.get("is_superuser", False))
        if raw_id != str(user_id) and not is_superuser:
            raise ClientException(detail="The user doesn't have enough privileges", status_code=403)

        user = await user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundException(detail="User not found.")
        return _model_to_read(user)

    # ------------------------------------------------------------------
    # PATCH /{user_id} — Superadmin only: Update user role / status
    # ------------------------------------------------------------------

    @patch(
        path=["/{user_id:uuid}", "/{user_id:uuid}/role"],
        guards=[SuperuserGuard()],
        status_code=HTTP_200_OK,
        summary="Update user role/status (Admin)",
        description="Superadmin endpoint to assign roles, activate/deactivate accounts, or update profiles.",
    )
    async def update_user_admin(
        self,
        user_id: uuid.UUID,
        data: UserAdminUpdate,
        user_repo: IUserRepository,
    ) -> UserRead:
        user = await user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundException(detail="User not found.")

        if data.email and data.email != user.email:
            existing = await user_repo.get_by_email(data.email)
            if existing and existing.id != user_id:
                raise ClientException(detail="User with this email already exists", status_code=409)
            user.email = data.email

        if data.full_name is not None:
            user.full_name = data.full_name
        if data.password is not None:
            user.hashed_password = get_password_hash(data.password)
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.is_superuser is not None:
            user.is_superuser = data.is_superuser

        updated = await user_repo.update(user)
        return _model_to_read(updated)

    # ------------------------------------------------------------------
    # DELETE /{user_id} — Superadmin only: Delete user
    # ------------------------------------------------------------------

    @delete(
        path="/{user_id:uuid}",
        guards=[SuperuserGuard()],
        status_code=HTTP_200_OK,
        summary="Delete user (Admin)",
        description="Superadmin endpoint to permanently remove a user account.",
    )
    async def delete_user(
        self,
        user_id: uuid.UUID,
        request: Request,
        user_repo: IUserRepository,
    ) -> Message:
        raw_id: str = request.scope.get("user_id", "")
        if raw_id and raw_id == str(user_id):
            raise ClientException(
                detail="Super users are not allowed to delete themselves",
                status_code=403,
            )

        deleted = await user_repo.delete(user_id)
        if not deleted:
            raise NotFoundException(detail="User not found.")
        return Message(message="User deleted successfully")
