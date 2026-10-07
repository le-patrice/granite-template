import structlog
from litestar import Litestar

from app.adapters.cache.valkey_service import valkey_store
from app.core.csrf import CSRFOriginMiddleware
from app.core.database import alchemy_plugin
from app.core.idempotency import IdempotencyMiddleware
from app.core.logging import RequestLoggingMiddleware, setup_logging
from app.core.metrics import PrometheusMetricsMiddleware, metrics_endpoint
from app.core.openapi import openapi_config
from app.core.rate_limit import SlidingWindowRateLimitMiddleware
from app.core.settings import settings
from app.presentation.api.router import api_router
from app.presentation.api.v1.health_controller import HealthController

# Initialize structured logging engine
setup_logging()
logger = structlog.get_logger("app.bootstrap")


def init_sentry() -> None:
    """Initialize Sentry APM and error tracking if DSN is configured."""
    if not settings.SENTRY_DSN:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.litestar import LitestarIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.SENTRY_ENVIRONMENT,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
            integrations=[
                LitestarIntegration(),
                SqlalchemyIntegration(),
            ],
            send_default_pii=False,
        )
        logger.info("sentry.initialized", environment=settings.SENTRY_ENVIRONMENT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("sentry.init_failed", error=str(exc))


# Initialize Sentry before app construction
init_sentry()


async def init_admin_user() -> None:
    """Ensure initial superuser exists upon platform startup."""
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.adapters.postgres.user_repository import PostgresUserRepository
        from app.core.security import get_password_hash
        from app.domain.users.models import User

        email = settings.FIRST_SUPERUSER_EMAIL
        password = settings.FIRST_SUPERUSER_PASSWORD

        if not email or not password:
            logger.warning(
                "superuser_startup_seed_skipped",
                reason="FIRST_SUPERUSER_EMAIL or FIRST_SUPERUSER_PASSWORD not configured",
            )
            return

        engine = create_async_engine(settings.DATABASE_URL)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            repo = PostgresUserRepository(session=session)
            existing = await repo.get_by_email(email)
            if not existing:
                import uuid

                default_org_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
                superuser = User(
                    email=email,
                    hashed_password=get_password_hash(password),
                    full_name=settings.FIRST_SUPERUSER_NAME,
                    is_superuser=True,
                    is_active=True,
                    organization_id=default_org_id,
                    role="superadmin",
                )
                await repo.add(superuser)
                await session.commit()
                logger.info("superuser_seeded_at_startup", email=email)
        await engine.dispose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("superuser_startup_seed_deferred", error=str(exc))


async def verify_runtime_role_security() -> None:
    """Verify that if connecting as app_runtime, the role is non-superuser and has no bypassrls."""
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(settings.DATABASE_URL)
        async with engine.connect() as conn:
            res = await conn.execute(
                text(
                    "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
                )
            )
            row = res.fetchone()
            if row:
                rolname, is_super, bypass_rls = row[0], bool(row[1]), bool(row[2])
                if rolname == "app_runtime" and (is_super or bypass_rls):
                    logger.error(
                        "security.runtime_role_misconfigured",
                        role=rolname,
                        rolsuper=is_super,
                        rolbypassrls=bypass_rls,
                    )
                    raise RuntimeError(
                        "Security violation: app_runtime role has SUPERUSER or BYPASSRLS privileges!"
                    )
                logger.info(
                    "security.runtime_role_verified",
                    role=rolname,
                    rolsuper=is_super,
                    rolbypassrls=bypass_rls,
                )
        await engine.dispose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("security.runtime_role_check_deferred", error=str(exc))


middleware_list = [
    RequestLoggingMiddleware,
    CSRFOriginMiddleware,
    PrometheusMetricsMiddleware,
    IdempotencyMiddleware,
]

if settings.RATE_LIMIT_ENABLED:
    middleware_list.append(SlidingWindowRateLimitMiddleware)


app = Litestar(
    route_handlers=[HealthController, metrics_endpoint, api_router],
    plugins=[alchemy_plugin],
    middleware=middleware_list,
    stores={"valkey": valkey_store},
    openapi_config=openapi_config if settings.ENVIRONMENT != "production" else None,
    debug=settings.DEBUG,
    on_startup=[init_admin_user, verify_runtime_role_security],
)
