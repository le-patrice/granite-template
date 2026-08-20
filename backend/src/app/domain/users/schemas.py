import uuid

import msgspec


class UserCreate(msgspec.Struct, frozen=True):
    email: str
    password: str
    full_name: str


class UserAdminCreate(msgspec.Struct, frozen=True):
    email: str
    password: str
    full_name: str
    is_active: bool = True
    is_superuser: bool = False


class UserRead(msgspec.Struct, frozen=True):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool


class UserUpdate(msgspec.Struct, frozen=True):
    """Partial update payload for own profile — all fields optional."""

    full_name: str | None = None
    password: str | None = None


class UserAdminUpdate(msgspec.Struct, frozen=True):
    """Superadmin update payload for managing users & roles."""

    full_name: str | None = None
    password: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None


class TokenResponse(msgspec.Struct, frozen=True):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class LoginRequest(msgspec.Struct, frozen=True):
    email: str | None = None
    username: str | None = None
    password: str = ""
