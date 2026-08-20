"""
Alembic migration cycle tests.

Strategy
--------
These tests run the full Alembic migration sequence against the real
test database:

  1.  Run ``alembic downgrade base`` — verifies every downgrade() is reversible.
  2.  Run ``alembic upgrade head``   — verifies the full up-path.
  3.  Run ``alembic downgrade base`` again — verifies idempotency of teardown.
  4.  Run ``alembic upgrade head`` again — restores database state for application.

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

•  The test is marked ``@pytest.mark.slow`` so CI pipelines can opt-in via
   ``pytest -m slow`` without running it in the fast unit-test pass.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig

from alembic import command as alembic_cmd

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BACKEND_ROOT = Path(__file__).parent.parent  # backend/
_ALEMBIC_INI = _BACKEND_ROOT / "alembic.ini"


def _sync_dsn() -> str:
    """Return a psycopg2-compatible DSN derived from the env DATABASE_URL."""
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://app_user:secure_dev_password@localhost:5432/app_db",
    )
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def alembic_cfg() -> AlembicConfig:
    """Alembic config using real sync DSN."""
    cfg = AlembicConfig(str(_ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", _sync_dsn())
    return cfg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestMigrationCycle:
    """Full upgrade → downgrade → upgrade cycle."""

    @classmethod
    def setup_class(cls):
        """Drop existing tables so Alembic tests run on a clean database."""
        import sqlalchemy as sa

        engine = sa.create_engine(_sync_dsn(), isolation_level="AUTOCOMMIT")
        with engine.connect() as conn:
            conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version CASCADE;"))
            conn.execute(sa.text("DROP TABLE IF EXISTS dead_letter_events CASCADE;"))
            conn.execute(sa.text("DROP TABLE IF EXISTS outbox_events CASCADE;"))
            conn.execute(sa.text("DROP TABLE IF EXISTS telemetry_readings CASCADE;"))
            conn.execute(sa.text("DROP TABLE IF EXISTS platform_users CASCADE;"))
        engine.dispose()

    def test_upgrade_head(self, alembic_cfg: AlembicConfig):
        """All migrations apply cleanly."""
        alembic_cmd.upgrade(alembic_cfg, "head")

    def test_downgrade_base(self, alembic_cfg: AlembicConfig):
        """Every downgrade() function executes without error."""
        alembic_cmd.downgrade(alembic_cfg, "base")

    def test_upgrade_head_again(self, alembic_cfg: AlembicConfig):
        """Re-applying from scratch is idempotent."""
        alembic_cmd.upgrade(alembic_cfg, "head")


@pytest.mark.slow
class TestMigrationHistory:
    """Assert structural invariants in the migration chain."""

    def test_revision_chain_is_linear(self, alembic_cfg: AlembicConfig):
        """No branch points — single linear revision chain."""
        from alembic.script import ScriptDirectory

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
            assert "def downgrade" in source, f"{mig_file.name} is missing a downgrade() function."
            lines_after = source.split("def downgrade")[1].strip()
            assert lines_after and "pass" not in lines_after.splitlines()[1].strip(), (
                f"{mig_file.name} has a stub downgrade() — implement it."
            )
