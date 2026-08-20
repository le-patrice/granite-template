"""
add_gin_trgm_indexes_and_telemetry_table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-20 00:00:00.000000 UTC

Changes
-------
1. GIN trigram indexes on platform_users.email and platform_users.full_name
   for fast ILIKE / similarity search.
2. telemetry_readings table matching app.domain.telemetry.models.TelemetryReading,
   with a composite B-Tree index on (transformer_id, recorded_at).
"""
from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. GIN trigram indexes on platform_users
    # ------------------------------------------------------------------
    # CONCURRENTLY cannot run inside a transaction; Alembic wraps migrations
    # in transactions by default, so we use plain CREATE INDEX here.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_platform_users_email_trgm
        ON platform_users
        USING GIN (email gin_trgm_ops);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_platform_users_full_name_trgm
        ON platform_users
        USING GIN (full_name gin_trgm_ops);
        """
    )

    # ------------------------------------------------------------------
    # 2. telemetry_readings table
    # ------------------------------------------------------------------
    op.create_table(
        "telemetry_readings",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("transformer_id", sa.String(128), nullable=False),
        sa.Column("voltage_v",     sa.Float(), nullable=False),
        sa.Column("current_a",     sa.Float(), nullable=False),
        sa.Column("power_factor",  sa.Float(), nullable=False),
        sa.Column("frequency_hz",  sa.Float(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # B-Tree index on transformer_id alone (equality lookups)
    op.create_index(
        "ix_telemetry_transformer_id",
        "telemetry_readings",
        ["transformer_id"],
        unique=False,
    )

    # B-Tree index on recorded_at alone (time-range scans)
    op.create_index(
        "ix_telemetry_recorded_at",
        "telemetry_readings",
        ["recorded_at"],
        unique=False,
    )

    # Composite index: WHERE transformer_id = :id AND recorded_at BETWEEN ...
    # TimescaleDB will further prune partitions on recorded_at after
    # SELECT create_hypertable('telemetry_readings', 'recorded_at') is run.
    op.create_index(
        "ix_telemetry_transformer_recorded",
        "telemetry_readings",
        ["transformer_id", "recorded_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_transformer_recorded", table_name="telemetry_readings")
    op.drop_index("ix_telemetry_recorded_at",          table_name="telemetry_readings")
    op.drop_index("ix_telemetry_transformer_id",       table_name="telemetry_readings")
    op.drop_table("telemetry_readings")

    op.execute("DROP INDEX IF EXISTS ix_platform_users_full_name_trgm;")
    op.execute("DROP INDEX IF EXISTS ix_platform_users_email_trgm;")
