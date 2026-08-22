"""
Users management and administration controller.

Provides full parity with the reference FastAPI endpoints:
  • POST /users/register & POST /users/signup  – Open self-registration (no JWT required)
  • GET /users/me                             – Get current user profile
  • PATCH /users/me                           – Update current user profile
  • PATCH /users/me/password                  – Change current user password
  • DELETE /users/me                          – Delete own account (standard users only)
  • POST /users                               – Superadmin only: Provision new user with roles
  • GET /users                                – Superadmin only: Paginated user list + count
  • GET /users/{user_id}                      – Superadmin only: Retrieve user by ID
  • PATCH /users/{user_id}                    – Superadmin only: Update user profile
  • PATCH /users/{user_id}/role               – Superadmin only: Update user role / status
  • DELETE /users/{user_id}                   – Superadmin only: Delete user
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


async def provide_user_repo(db_session: AsyncSession) -> IUserRepository:
    return PostgresUserRepository(session=db_session)


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

    async def _create_open_user(
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

    async def _update_admin_user(
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
    # POST /register & /signup — open self-registration
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
        return await self._create_open_user(data, user_repo)

    @post(
        path="/signup",
        status_code=HTTP_201_CREATED,
        summary="Open user signup",
        description="Create a new standard (non-superuser) account. No JWT required.",
    )
    async def signup(
        self,
        data: UserCreate,
        user_repo: IUserRepository,
    ) -> UserRead:
        return await self._create_open_user(data, user_repo)

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
        description="Update the authenticated user's full_name, email, or password.",
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
        user = await user_repo.get_by_id(uuid.UUID(raw_id))
        if user is None:
            raise NotFoundException(detail="User not found.")

        if data.email and data.email != user.email:
            existing = await user_repo.get_by_email(data.email)
            if existing and existing.id != user.id:
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
        description="Change password for the currently authenticated user.",
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

        if not await verify_password_async(data.current_password, user.hashed_password):
            raise ClientException(detail="Incorrect password", status_code=400)

        if data.current_password == data.new_password:
            raise ClientException(
                detail="New password cannot be the same as the current password",
                status_code=400,
            )

        user.hashed_password = get_password_hash(data.new_password)
        await user_repo.update(user)
        return Message(message="Password updated successfully")

    # ------------------------------------------------------------------
    # DELETE /me — Standard users only: Delete own account
    # ------------------------------------------------------------------

    @delete(
        path="/me",
        guards=[JWTAuthGuard()],
        status_code=HTTP_200_OK,
        summary="Delete own account",
        description="Standard users can delete their own account. Superusers are forbidden.",
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
        path="",
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
        path="",
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
        path="/{user_id:uuid}",
        guards=[SuperuserGuard()],
        status_code=HTTP_200_OK,
        summary="Update user details (Admin)",
        description="Superadmin endpoint to assign roles, activate/deactivate accounts, or update profiles.",
    )
    async def update_user_admin(
        self,
        user_id: uuid.UUID,
        data: UserAdminUpdate,
        user_repo: IUserRepository,
    ) -> UserRead:
        return await self._update_admin_user(user_id, data, user_repo)

    @patch(
        path="/{user_id:uuid}/role",
        guards=[SuperuserGuard()],
        status_code=HTTP_200_OK,
        summary="Update user role/status (Admin)",
        description="Superadmin endpoint to assign roles, activate/deactivate accounts, or update profiles.",
    )
    async def update_user_role_admin(
        self,
        user_id: uuid.UUID,
        data: UserAdminUpdate,
        user_repo: IUserRepository,
    ) -> UserRead:
        return await self._update_admin_user(user_id, data, user_repo)

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
