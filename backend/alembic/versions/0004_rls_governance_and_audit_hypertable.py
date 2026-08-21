"""
rls_governance_and_audit_hypertable

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-21 12:00:00.000000 UTC

Changes
-------
1. Adds aggregate_type and aggregate_id columns to outbox_events table.
2. Creates audit_logs table and converts it to a TimescaleDB hypertable (if extension present).
3. Creates generic process_audit_log() PostgreSQL trigger function and attaches it to platform_users.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Update outbox_events with aggregate tracking
    # ------------------------------------------------------------------
    op.add_column(
        "outbox_events",
        sa.Column("aggregate_type", sa.String(length=128), nullable=False, server_default="general"),
    )
    op.add_column(
        "outbox_events",
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_outbox_events_aggregate_type", "outbox_events", ["aggregate_type"])
    op.create_index("ix_outbox_events_aggregate_id", "outbox_events", ["aggregate_id"])

    # ------------------------------------------------------------------
    # 2. Create immutable audit_logs table (safe idempotent DDL)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            table_name VARCHAR(128) NOT NULL,
            operation VARCHAR(16) NOT NULL,
            record_id UUID NOT NULL,
            old_data JSONB,
            new_data JSONB,
            changed_by VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS ix_audit_logs_table_created ON audit_logs (table_name, created_at);
        CREATE INDEX IF NOT EXISTS ix_audit_logs_record_created ON audit_logs (record_id, created_at);
        """
    )

    # ------------------------------------------------------------------
    # 3. Convert audit_logs to TimescaleDB hypertable (if available)
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                PERFORM create_hypertable('audit_logs', 'created_at', if_not_exists => TRUE);
            END IF;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'TimescaleDB hypertable creation on audit_logs skipped: %', SQLERRM;
        END $$;
        """
    )

    # ------------------------------------------------------------------
    # 4. Create generic audit trigger function and attach to platform_users
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION process_audit_log() RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO audit_logs (
                id,
                table_name,
                operation,
                record_id,
                old_data,
                new_data,
                changed_by,
                created_at
            ) VALUES (
                gen_random_uuid(),
                TG_TABLE_NAME,
                TG_OP,
                CASE
                    WHEN TG_OP = 'DELETE' THEN OLD.id
                    ELSE NEW.id
                END,
                CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) ELSE NULL END,
                CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) ELSE NULL END,
                NULLIF(current_setting('app.current_user_id', true), ''),
                NOW()
            );
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_audit_platform_users ON platform_users;
        CREATE TRIGGER trg_audit_platform_users
        AFTER INSERT OR UPDATE OR DELETE ON platform_users
        FOR EACH ROW EXECUTE FUNCTION process_audit_log();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_platform_users ON platform_users;")
    op.execute("DROP FUNCTION IF EXISTS process_audit_log();")
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE;")
    op.drop_index("ix_outbox_events_aggregate_id", table_name="outbox_events")
    op.drop_index("ix_outbox_events_aggregate_type", table_name="outbox_events")
    op.drop_column("outbox_events", "aggregate_id")
    op.drop_column("outbox_events", "aggregate_type")
