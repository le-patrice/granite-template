import uuid
from typing import Optional
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
    full_name: Optional[str] = None
    password: Optional[str] = None


class UserAdminUpdate(msgspec.Struct, frozen=True):
    """Superadmin update payload for managing users & roles."""
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class TokenResponse(msgspec.Struct, frozen=True):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600


class LoginRequest(msgspec.Struct, frozen=True):
    email: Optional[str] = None
    username: Optional[str] = None
    password: str = ""
