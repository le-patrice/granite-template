import uuid
import msgspec
from typing import Optional

class UserCreate(msgspec.Struct, frozen=True):
    email: str
    password: str
    full_name: str

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

class TokenResponse(msgspec.Struct, frozen=True):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(msgspec.Struct, frozen=True):
    email: str
    password: str
