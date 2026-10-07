"""
harden_rls_and_multi_tenant_outbox

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-07 12:00:00.000000 UTC

Changes
-------
1. Adds organization_id column and index to outbox_events table for tenant-scoped outbox dispatching.
2. Adds organization_id column and index to audit_logs hypertable for multi-tenant audit trail isolation.
3. Updates process_audit_log() PostgreSQL trigger function to populate organization_id from transaction context.
4. Creates reusable attach_tenant_rls(target_table TEXT) function that enforces FORCE ROW LEVEL SECURITY.
5. Attaches tenant isolation and FORCE ROW LEVEL SECURITY to audit_logs.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Multi-tenant column on outbox_events
    # ------------------------------------------------------------------
    op.add_column(
        "outbox_events",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_outbox_events_organization_id", "outbox_events", ["organization_id"])

    # ------------------------------------------------------------------
    # 2. Multi-tenant column on audit_logs
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS organization_id UUID;
        CREATE INDEX IF NOT EXISTS ix_audit_logs_organization_id ON audit_logs (organization_id);
        """
    )

    # ------------------------------------------------------------------
    # 3. Update process_audit_log() to populate organization_id
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
                organization_id,
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
                NULLIF(current_setting('app.current_tenant_id', true), '')::uuid,
                NOW()
            );
            RETURN COALESCE(NEW, OLD);
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # ------------------------------------------------------------------
    # 4. Reusable attach_tenant_rls helper enforcing FORCE ROW LEVEL SECURITY
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION attach_tenant_rls(target_table TEXT) RETURNS VOID AS $$
        BEGIN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', target_table);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', target_table);
            EXECUTE format(
                'DROP POLICY IF EXISTS tenant_isolation_policy ON %I; ' ||
                'CREATE POLICY tenant_isolation_policy ON %I ' ||
                'FOR ALL TO PUBLIC ' ||
                'USING ( ' ||
                '    current_setting(''app.current_role'', true) = ''superadmin'' ' ||
                '    OR organization_id IS NULL ' ||
                '    OR organization_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::uuid ' ||
                ') ' ||
                'WITH CHECK ( ' ||
                '    current_setting(''app.current_role'', true) = ''superadmin'' ' ||
                '    OR organization_id IS NULL ' ||
                '    OR organization_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::uuid ' ||
                ');',
                target_table, target_table
            );
        END;
        $$ LANGUAGE plpgsql;

        -- Attach tenant RLS governance to audit_logs
        SELECT attach_tenant_rls('audit_logs');
        """
    )


def downgrade() -> None:
    # Disable RLS and drop policy on audit_logs
    op.execute(
        """
        DROP POLICY IF EXISTS tenant_isolation_policy ON audit_logs;
        ALTER TABLE audit_logs NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY;
        DROP FUNCTION IF EXISTS attach_tenant_rls(TEXT);
        """
    )

    # Revert trigger function to previous definition
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
        """
    )

    # Drop audit_logs organization_id
    op.execute(
        """
        DROP INDEX IF EXISTS ix_audit_logs_organization_id;
        ALTER TABLE audit_logs DROP COLUMN IF EXISTS organization_id;
        """
    )

    # Drop outbox_events organization_id
    op.drop_index("ix_outbox_events_organization_id", table_name="outbox_events")
    op.drop_column("outbox_events", "organization_id")
