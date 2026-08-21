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

from advanced_alchemy.config import AsyncSessionConfig, EngineConfig
from advanced_alchemy.extensions.litestar.plugins import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
)
from sqlalchemy import event, text
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
    user_id = str(session.info.get("user_id") or "")
    tenant_id = str(session.info.get("tenant_id") or "")
    is_super = session.info.get("is_superuser", False)
    role = str(session.info.get("role") or ("superadmin" if is_super else "guest"))

    # Execute parameterized set_config call on the active transaction connection
    connection.execute(  # type: ignore[attr-defined]
        text(
            "SELECT set_config('app.current_user_id', :user_id, true), "
            "set_config('app.current_tenant_id', :tenant_id, true), "
            "set_config('app.current_role', :role, true)"
        ),
        {"user_id": user_id, "tenant_id": tenant_id, "role": role},
    )
