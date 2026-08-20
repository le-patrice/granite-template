import uuid

from advanced_alchemy.repository import SQLAlchemyAsyncRepository
from sqlalchemy import select

from app.domain.users.contracts import IUserRepository
from app.domain.users.models import User


class PostgresUserRepository(SQLAlchemyAsyncRepository[User], IUserRepository):
    model_type = User

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.get_one_or_none(id=user_id)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        return await self.add(user, auto_commit=True)

    async def update(self, user: User) -> User:
        # Delegate to advanced-alchemy's parent update implementation with auto_commit=True.
        return await super().update(user, auto_commit=True)

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[User]:
        statement = select(User).offset(offset).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def delete(self, user_id: uuid.UUID) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False
        await super().delete(user_id, auto_commit=True)
        return True
