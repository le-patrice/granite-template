from abc import ABC, abstractmethod
import uuid
from app.domain.users.models import User


class IUserRepository(ABC):
    @abstractmethod
    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None:
        pass

    @abstractmethod
    async def create(self, user: User) -> User:
        pass

    @abstractmethod
    async def update(self, user: User) -> User:
        pass

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        pass

    @abstractmethod
    async def delete(self, user_id: uuid.UUID) -> bool:
        pass
