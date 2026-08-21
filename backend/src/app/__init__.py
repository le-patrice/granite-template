import structlog
from litestar import Litestar

from app.adapters.cache.valkey_service import valkey_store
from app.core.database import alchemy_plugin
from app.core.idempotency import IdempotencyMiddleware
from app.core.logging import RequestLoggingMiddleware, setup_logging
from app.core.metrics import PrometheusMetricsMiddleware, metrics_endpoint
from app.core.openapi import openapi_config
from app.core.settings import settings
from app.presentation.api.router import api_router
from app.presentation.api.v1.health_controller import HealthController

# Initialize structured logging engine
setup_logging()
logger = structlog.get_logger("app.bootstrap")


async def init_admin_user() -> None:
    """Ensure initial superuser exists upon platform startup."""
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.adapters.postgres.user_repository import PostgresUserRepository
        from app.core.security import get_password_hash
        from app.domain.users.models import User

        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            repo = PostgresUserRepository(session=session)
            existing = await repo.get_by_email(settings.FIRST_SUPERUSER_EMAIL)
            if not existing:
                superuser = User(
                    email=settings.FIRST_SUPERUSER_EMAIL,
                    hashed_password=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
                    full_name=settings.FIRST_SUPERUSER_NAME,
                    is_superuser=True,
                    is_active=True,
                )
                await repo.add(superuser)
                await session.commit()
                logger.info("superuser_seeded_at_startup", email=settings.FIRST_SUPERUSER_EMAIL)
        await engine.dispose()
    except (OSError, RuntimeError) as exc:
        logger.warning("superuser_startup_seed_deferred", error=str(exc))


app = Litestar(
    route_handlers=[HealthController, metrics_endpoint, api_router],
    plugins=[alchemy_plugin],
    middleware=[RequestLoggingMiddleware, PrometheusMetricsMiddleware, IdempotencyMiddleware],
    stores={"valkey": valkey_store},
    openapi_config=openapi_config if settings.ENVIRONMENT != "production" else None,
    debug=settings.DEBUG,
    on_startup=[init_admin_user],
)
