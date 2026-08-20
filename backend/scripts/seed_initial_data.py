import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.security import get_password_hash
from app.core.settings import settings
from app.domain.users.models import User
from app.adapters.postgres.user_repository import PostgresUserRepository

async def seed_superuser() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    async with session_factory() as session:
        repo = PostgresUserRepository(session=session)
        existing_user = await repo.get_by_email(settings.FIRST_SUPERUSER_EMAIL)
        
        if existing_user:
            print(f"Superuser '{settings.FIRST_SUPERUSER_EMAIL}' already exists. Skipping.")
            return

        print(f"Seeding Initial Superuser: {settings.FIRST_SUPERUSER_EMAIL}")
        superuser = User(
            email=settings.FIRST_SUPERUSER_EMAIL,
            hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
            full_name=settings.FIRST_SUPERUSER_NAME,
            is_superuser=True,
            is_active=True,
        )
        await repo.add(superuser)
        await session.commit()
        print("Superuser successfully seeded!")

if __name__ == "__main__":
    asyncio.run(seed_superuser())
