"""
Database engine & session configuration — production / PgBouncer hardened.

Key settings
------------
pool_pre_ping=True
    Emits a ``SELECT 1`` before each checkout to evict stale connections.
    Mandatory when sitting behind PgBouncer in transaction-pooling mode.

pool_recycle=1800
    Recycle connections after 30 minutes so PgBouncer's ``server_lifetime``
    never kills a connection the pool still thinks is alive.

statement_cache_size=0
    asyncpg caches prepared statements per connection by default, which is
    incompatible with PgBouncer (statements are not shared across pool
    connections). Setting this to 0 disables the per-connection cache so
    every statement is sent as a one-off query — correct for PgBouncer
    transaction-pooling mode.

RLS Session Context (after_begin hook)
-------------------------------------
Executes `SELECT set_config('app.current_user_id', ...), set_config('app.current_tenant_id', ...), set_config('app.current_role', ...)`
with `is_local=True` on every transaction begin. Because it is strictly transaction-local,
session context is automatically cleared on COMMIT/ROLLBACK, guaranteeing 100% PgBouncer safety.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from advanced_alchemy.config import AsyncSessionConfig, EngineConfig
from advanced_alchemy.extensions.litestar.plugins import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
)
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.settings import settings

# ---------------------------------------------------------------------------
# SQLAlchemy Configuration
# ---------------------------------------------------------------------------

db_config = SQLAlchemyAsyncConfig(
    connection_string=settings.DATABASE_URL,
    session_config=AsyncSessionConfig(expire_on_commit=False),
    engine_config=EngineConfig(
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        connect_args={"statement_cache_size": 0},
    ),
)

alchemy_plugin = SQLAlchemyInitPlugin(config=db_config)


import contextvars

# ---------------------------------------------------------------------------
# Request Context Variables for Database RLS Context
# ---------------------------------------------------------------------------
current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_user_id", default="")
current_tenant_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_tenant_id", default=""
)
current_role: contextvars.ContextVar[str] = contextvars.ContextVar("current_role", default="")
current_is_superuser: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "current_is_superuser", default=False
)


# ---------------------------------------------------------------------------
# PgBouncer-Safe Tenant & Role Context Listener for PostgreSQL RLS
# ---------------------------------------------------------------------------


@event.listens_for(Session, "after_begin")
def set_tenant_context(session: Session, transaction: object, connection: object) -> None:
    """
    Sets transaction-local session context for PostgreSQL Row-Level Security (RLS).
    Uses PostgreSQL set_config(..., is_local=true) which is strictly transaction-local,
    ensuring 100% safety with PgBouncer transaction-pooling mode.
    """
    user_id = str(session.info.get("user_id") or current_user_id.get())
    tenant_id = str(session.info.get("tenant_id") or current_tenant_id.get())
    is_super = session.info.get("is_superuser")
    if is_super is None:
        is_super = current_is_superuser.get()
    default_role = "superadmin" if is_super else ("user" if user_id else "guest")
    role = str(session.info.get("role") or current_role.get() or default_role)

    # Execute parameterized set_config call on the active transaction connection
    connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT set_config('app.current_user_id', :user_id, true), "
            "set_config('app.current_tenant_id', :tenant_id, true), "
            "set_config('app.current_role', :role, true)"
        ),
        {"user_id": user_id, "tenant_id": tenant_id, "role": role},
    )


# ---------------------------------------------------------------------------
# Background Task & Worker Tenant Session Context Manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def tenant_session(
    tenant_id: str | uuid.UUID,
    user_id: str | uuid.UUID | None = None,
    role: str = "user",
    is_superuser: bool = False,
    session: AsyncSession | None = None,
) -> AsyncIterator[AsyncSession]:
    """
    Async context manager that yields an AsyncSession scoped to a specific tenant.
    Populates both contextvars and session.info, ensuring 100% isolation in SAQ
    background jobs, outbox relays, and event subscribers without context leaks.
    """
    token_tenant = current_tenant_id.set(str(tenant_id))
    token_user = current_user_id.set(str(user_id) if user_id else "")
    token_role = current_role.set(role)
    token_super = current_is_superuser.set(is_superuser)
    try:
        if session is not None:
            session.info["tenant_id"] = str(tenant_id)
            if user_id:
                session.info["user_id"] = str(user_id)
            session.info["role"] = role
            session.info["is_superuser"] = is_superuser
            yield session
        else:
            async with db_config.get_session() as s:
                s.info["tenant_id"] = str(tenant_id)
                if user_id:
                    s.info["user_id"] = str(user_id)
                s.info["role"] = role
                s.info["is_superuser"] = is_superuser
                yield s
    finally:
        current_tenant_id.reset(token_tenant)
        current_user_id.reset(token_user)
        current_role.reset(token_role)
        current_is_superuser.reset(token_super)
