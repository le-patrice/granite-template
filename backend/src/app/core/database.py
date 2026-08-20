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
    connections).  Setting this to 0 disables the per-connection cache so
    every statement is sent as a one-off query — correct for PgBouncer
    transaction-pooling mode.

connect_args
    Passed directly to asyncpg.  ``statement_cache_size=0`` lives here.

autocommit / expire_on_commit=False
    Each handler gets a clean session; objects remain usable after commit
    (important for msgspec serialisation in the response phase).
"""

from advanced_alchemy.config import AsyncSessionConfig, EngineConfig
from advanced_alchemy.extensions.litestar.plugins import (
    SQLAlchemyAsyncConfig,
    SQLAlchemyInitPlugin,
)

from app.core.settings import settings

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
