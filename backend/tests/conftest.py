"""
Test suite fixtures.

Architecture
------------
•  The test database is the real Postgres container (same DATABASE_URL as the
   app). Each test wraps its writes in a SAVEPOINT via session.begin_nested()
   and rolls it back on teardown — no schema changes or data bleed between
   tests.

•  Valkey calls are mocked at the module boundary so tests remain hermetic and
   fast even when Valkey is unavailable during CI.

•  The AsyncTestClient starts the full Litestar ASGI app (with lifespan events)
   so middleware, guards, DI, and plugins all participate in every request.

Requires in pyproject.toml [dev]:
    pytest>=8.2
    pytest-asyncio>=0.23
    httpx>=0.27
"""
import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from litestar.testing import AsyncTestClient
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    AsyncTransaction,
    create_async_engine,
)

from app import app as litestar_app
from app.core.settings import settings

# ---------------------------------------------------------------------------
# Event-loop: one shared loop for the whole test session.
# pytest-asyncio >= 0.21 requires explicit asyncio_mode in pytest.ini / pyproject
# or the loop_scope kwarg shown here.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop so all async fixtures share the same loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# Database engine — created once per session, never pooled in tests.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def async_engine():
    """
    Async engine connected to the same DATABASE_URL the application uses.
    NullPool is mandatory for test isolation: each connection is independent
    so nested transactions work correctly.
    """
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        settings.DATABASE_URL,
        poolclass=NullPool,
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def ensure_db_schema(async_engine):
    """Ensure all SQLAlchemy declarative tables exist in database before running tests."""
    from app.domain.base import Base
    import app.domain.users.models  # noqa: F401
    import app.domain.telemetry.models  # noqa: F401
    import app.domain.events.models  # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


# ---------------------------------------------------------------------------
# Transactional rollback session — one per test function.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Wraps every test in a savepoint (nested transaction).

    Strategy
    --------
    1.  Open a raw connection and start an outer TRANSACTION.
    2.  Bind an AsyncSession to that connection.
    3.  Begin a SAVEPOINT inside the outer transaction.
    4.  Yield the session for the test to use.
    5.  Roll back to the savepoint on teardown — database state is pristine.
    6.  Roll back the outer transaction and close the connection.

    This means actual COMMIT calls inside the application code commit to the
    savepoint only, not to the real database.
    """
    async with async_engine.connect() as conn:
        outer_tx: AsyncTransaction = await conn.begin()

        session = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")

        await session.begin_nested()  # SAVEPOINT

        yield session

        await session.rollback()      # roll back to savepoint
        await outer_tx.rollback()     # roll back outer transaction
        await session.close()


# ---------------------------------------------------------------------------
# Valkey mock — prevents real network calls to Valkey during unit tests.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_valkey():
    """
    Patch both Valkey helper functions so tests never require a live Valkey
    instance.  Applied automatically (autouse=True) to every test.
    """
    with (
        patch(
            "app.adapters.cache.valkey_service.set_transformer_state",
            new_callable=AsyncMock,
        ) as mock_set,
        patch(
            "app.adapters.cache.valkey_service.get_transformer_state",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_get,
    ):
        yield {"set": mock_set, "get": mock_get}


# ---------------------------------------------------------------------------
# Litestar AsyncTestClient — boots the full ASGI app with lifespan.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client wired to the full Litestar app.

    The AsyncTestClient starts the app's lifespan (triggering startup /
    shutdown hooks for the DB plugin, stores, etc.) and tears it down
    cleanly after each test.
    """
    async with AsyncTestClient(app=litestar_app) as client:
        yield client


# ---------------------------------------------------------------------------
# Convenience: register a fresh user and return (email, password, token).
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture()
async def registered_user(async_client: AsyncClient) -> dict[str, Any]:
    """
    Register a unique test user and return a dict with:
        email, password, full_name, token
    """
    uid = uuid.uuid4().hex[:8]
    payload = {
        "email": f"test.{uid}@example.com",
        "password": "TestPass!2026",
        "full_name": f"Test User {uid}",
    }
    reg_resp = await async_client.post("/api/v1/users/register", json=payload)
    assert reg_resp.status_code == 201, reg_resp.text

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["password"]},
    )
    assert login_resp.status_code == 201, login_resp.text
    token = login_resp.json()["access_token"]

    return {**payload, "token": token, "id": reg_resp.json()["id"]}
