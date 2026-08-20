"""
timescaledb_policies_and_outbox

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-20 00:00:00.000000 UTC

Changes
-------
1. Creates outbox_events and dead_letter_events tables.
2. Configures TimescaleDB automated compression (7 days) and retention (90 days) policies on telemetry_readings hypertable.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Outbox and Dead Letter Queue tables
    # ------------------------------------------------------------------
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_outbox_events_status", "outbox_events", ["status"])
    op.create_index("ix_outbox_events_event_type", "outbox_events", ["event_type"])
    op.create_index("ix_outbox_events_created_at", "outbox_events", ["created_at"])

    op.create_table(
        "dead_letter_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("original_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("error_trace", sa.Text(), nullable=False),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_dead_letter_events_original_event_id", "dead_letter_events", ["original_event_id"])

    # ------------------------------------------------------------------
    # 2. TimescaleDB compression and retention policies (safely guarded)
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                -- Enable compression on hypertable if not already enabled
                ALTER TABLE telemetry_readings SET (
                    timescaledb.compress,
                    timescaledb.compress_segmentby = 'transformer_id',
                    timescaledb.compress_orderby = 'recorded_at DESC'
                );

                -- Automated compression policy (> 7 days)
                PERFORM add_compression_policy('telemetry_readings', INTERVAL '7 days', if_not_exists => true);

                -- Automated data retention policy (> 90 days)
                PERFORM add_retention_policy('telemetry_readings', INTERVAL '90 days', if_not_exists => true);
            END IF;
        EXCEPTION WHEN OTHERS THEN
            -- In standard Postgres test environments where hypertable is a regular table, ignore
            RAISE NOTICE 'TimescaleDB policy application skipped: %', SQLERRM;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("dead_letter_events")
    op.drop_table("outbox_events")
