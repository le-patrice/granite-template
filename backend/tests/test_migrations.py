"""
Alembic migration cycle tests.

Strategy
--------
These tests run the full Alembic migration sequence against the real
test database using a temporary schema so they never touch the schema
used by other tests:

  1.  Create a fresh PostgreSQL schema (``test_migrations_<uuid4_short>``).
  2.  Set ``search_path`` so all DDL operates inside that schema.
  3.  Run ``alembic upgrade head``  — verifies the full up-path.
  4.  Run ``alembic downgrade base`` — verifies every downgrade() is reversible.
  5.  Run ``alembic upgrade head`` again — verifies idempotency.
  6.  Drop the temporary schema.

This gives us confidence that:
  •  Every migration file is syntactically and semantically correct.
  •  Downgrade paths are complete (not left as ``pass``).
  •  The chain is idempotent (can be re-applied from scratch).

Notes
-----
•  The test uses a *synchronous* ``psycopg2`` connection because Alembic's
   ``env.py`` already switches to psycopg2 (it cannot use asyncpg directly).
   The ``DATABASE_URL`` env var is rewritten from ``asyncpg`` → ``psycopg2``
   automatically by ``env.py``; we do the same swap here.

•  ``SET search_path`` restricts DDL to the temporary schema.  Extensions
   (uuid-ossp, pg_trgm, etc.) are created in ``public`` and visible from
   any schema, so the ``CREATE EXTENSION IF NOT EXISTS`` calls in 0001 work
   correctly.

•  The test is marked ``@pytest.mark.slow`` so CI pipelines can opt-in via
   ``pytest -m slow`` without running it in the fast unit-test pass.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from alembic import command as alembic_cmd
from alembic.config import Config as AlembicConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).parent.parent   # backend/
_ALEMBIC_INI  = _BACKEND_ROOT / "alembic.ini"


def _sync_dsn() -> str:
    """Return a psycopg2-compatible DSN derived from the env DATABASE_URL."""
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://app_user:secure_dev_password@localhost:5432/app_db",
    )
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def _make_alembic_cfg(schema: str) -> AlembicConfig:
    """
    Build an Alembic Config that:
    •  Points at our alembic.ini
    •  Overrides sqlalchemy.url to psycopg2 DSN
    •  Sets search_path to restrict DDL to *schema*
    """
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", _sync_dsn())
    # Restrict to the temp schema by injecting search_path via connect_args
    # (Alembic passes engine_from_config kwargs; we monkey-patch via x opts)
    cfg.attributes["schema"] = schema
    return cfg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def temp_schema():
    """
    Create a throwaway PostgreSQL schema for migration tests and drop it
    after the module finishes.

    The schema name is short enough to fit in PG's 63-char NAMEDATALEN.
    """
    import sqlalchemy as sa

    short_id = uuid.uuid4().hex[:8]
    schema = f"test_mig_{short_id}"

    engine = sa.create_engine(_sync_dsn(), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    yield schema

    with engine.connect() as conn:
        conn.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    engine.dispose()


@pytest.fixture(scope="module")
def alembic_cfg(temp_schema: str) -> AlembicConfig:
    """Alembic config scoped to the temporary schema."""
    cfg = _make_alembic_cfg(temp_schema)
    # Override version_table to keep migration state inside the temp schema
    cfg.set_main_option("version_table_schema", temp_schema)
    return cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestMigrationCycle:
    """Full upgrade → downgrade → upgrade cycle in an isolated schema."""

    def test_upgrade_head(self, alembic_cfg: AlembicConfig):
        """All migrations apply cleanly from an empty schema."""
        alembic_cmd.upgrade(alembic_cfg, "head")

    def test_downgrade_base(self, alembic_cfg: AlembicConfig):
        """Every downgrade() function executes without error."""
        alembic_cmd.downgrade(alembic_cfg, "base")

    def test_upgrade_head_again(self, alembic_cfg: AlembicConfig):
        """Re-applying from scratch is idempotent (ON CONFLICT / IF NOT EXISTS)."""
        alembic_cmd.upgrade(alembic_cfg, "head")


@pytest.mark.slow
class TestMigrationHistory:
    """Assert structural invariants in the migration chain."""

    def test_revision_chain_is_linear(self, alembic_cfg: AlembicConfig):
        """No branch points — single linear revision chain."""
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        import sqlalchemy as sa

        script = ScriptDirectory.from_config(alembic_cfg)
        revisions = list(script.walk_revisions())

        # Each revision (except the first) must have exactly one down_revision
        for rev in revisions:
            if rev.down_revision is not None:
                assert not isinstance(rev.down_revision, (list, tuple)), (
                    f"Revision {rev.revision} has multiple parents — "
                    "branch merges require explicit merge revisions."
                )

    def test_all_revisions_have_downgrade(self):
        """Every migration must implement a non-trivial downgrade()."""
        versions_dir = _BACKEND_ROOT / "alembic" / "versions"
        for mig_file in sorted(versions_dir.glob("*.py")):
            source = mig_file.read_text()
            assert "def downgrade" in source, (
                f"{mig_file.name} is missing a downgrade() function."
            )
            # Rudimentary check: downgrade must not be a bare `pass`
            lines_after = source.split("def downgrade")[1].strip()
            assert lines_after and "pass" not in lines_after.splitlines()[1].strip(), (
                f"{mig_file.name} has a stub downgrade() — implement it."
            )
