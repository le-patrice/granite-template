"""Alembic environment script.

Reads DATABASE_URL from the runtime environment so the same alembic.ini
works in every context (local venv, container, CI).

Domain models are imported here so autogenerate can detect new tables.
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Make app package importable (PYTHONPATH=/app/src inside the container,
# but also workable when run from the backend/ directory locally).
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

# ---------------------------------------------------------------------------
# Import every model module so SQLAlchemy's metadata knows about them.
# Add new model imports here as the project grows.
# ---------------------------------------------------------------------------
from app.domain.base import Base  # noqa: E402
import app.domain.users.models  # noqa: E402, F401  – registers User on Base.metadata
import app.domain.telemetry.models  # noqa: E402, F401  – registers TelemetryReading

# ---------------------------------------------------------------------------
# Standard Alembic boilerplate
# ---------------------------------------------------------------------------
config = context.config

# Override sqlalchemy.url from the DATABASE_URL environment variable.
# This keeps credentials out of alembic.ini entirely.
database_url = os.environ.get("DATABASE_URL", "")
if database_url:
    # asyncpg driver doesn't work with Alembic's sync engine; swap it out.
    sync_url = database_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    ).replace(
        "postgresql+asyncpg+ssl://", "postgresql+psycopg2://"
    )
    config.set_main_option("sqlalchemy.url", sync_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the MetaData object used by autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (no live DB connection required)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live DB connection)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
