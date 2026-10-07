"""
strict_rls_and_tenant_defaults

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07 14:00:00.000000 UTC

Changes
-------
1. Creates reusable attach_tenant_rls_strict(target_table TEXT) procedure
   for business domain tables without the nullable-tenant escape hatch
   (disallowing organization_id IS NULL).
"""

from alembic import op

revision: str = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Stricter tenant RLS procedure for business tables (no NULL hatch)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION attach_tenant_rls_strict(target_table TEXT) RETURNS VOID AS $$
        BEGIN
            EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', target_table);
            EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', target_table);
            EXECUTE format(
                'DROP POLICY IF EXISTS tenant_isolation_policy ON %I; ' ||
                'CREATE POLICY tenant_isolation_policy ON %I ' ||
                'FOR ALL TO PUBLIC ' ||
                'USING ( ' ||
                '    current_setting(''app.current_role'', true) = ''superadmin'' ' ||
                '    OR organization_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::uuid ' ||
                ') ' ||
                'WITH CHECK ( ' ||
                '    current_setting(''app.current_role'', true) = ''superadmin'' ' ||
                '    OR organization_id = NULLIF(current_setting(''app.current_tenant_id'', true), '''')::uuid ' ||
                ');',
                target_table, target_table
            );
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS attach_tenant_rls_strict(TEXT);")
