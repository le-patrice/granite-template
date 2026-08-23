import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.core.security import get_password_hash
from app.core.settings import settings
from app.domain.users.models import User
from app.adapters.postgres.user_repository import PostgresUserRepository


async def seed_superuser() -> None:
    email = settings.FIRST_SUPERUSER_EMAIL
    password = settings.FIRST_SUPERUSER_PASSWORD

    if not email or not password:
        raise ValueError(
            "FIRST_SUPERUSER_EMAIL and FIRST_SUPERUSER_PASSWORD environment settings are required for seeding."
        )

    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        repo = PostgresUserRepository(session=session)
        existing_user = await repo.get_by_email(email)

        if existing_user:
            print(f"Superuser '{email}' already exists. Skipping.")
            return

        print(f"Seeding Initial Superuser: {email}")
        superuser = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=settings.FIRST_SUPERUSER_NAME,
            is_superuser=True,
            is_active=True,
        )
        await repo.add(superuser)
        await session.commit()
        print("Superuser successfully seeded!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_superuser())

