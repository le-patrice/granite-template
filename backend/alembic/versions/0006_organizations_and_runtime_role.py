"""
organizations_and_runtime_role

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-07 13:00:00.000000 UTC

Changes
-------
1. Provisions non-superuser app_runtime role for application database queries to enforce RLS.
2. Creates organizations table and seeds default organization ('00000000-0000-0000-0000-000000000001').
3. Adds organization_id and role columns with indexes and defaults to platform_users.
4. Creates reusable attach_audit_trigger(target_table TEXT) migration helper.
"""

from alembic import op

revision: str = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Provision non-superuser app_runtime role for RLS enforcement
    # ------------------------------------------------------------------
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_runtime') THEN
                CREATE ROLE app_runtime WITH LOGIN PASSWORD 'secure_dev_password'
                NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            END IF;
        END $$;

        GRANT CONNECT ON DATABASE app_db TO app_runtime;
        GRANT USAGE ON SCHEMA public TO app_runtime;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_runtime;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_runtime;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_runtime;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO app_runtime;
        """
    )

    # ------------------------------------------------------------------
    # 2. Organizations table and default seed
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(255) NOT NULL UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS ix_organizations_slug ON organizations (slug);

        INSERT INTO organizations (id, name, slug)
        VALUES ('00000000-0000-0000-0000-000000000001', 'Default Organization', 'default-org')
        ON CONFLICT (slug) DO NOTHING;
        """
    )

    # ------------------------------------------------------------------
    # 3. Add organization_id and role to platform_users
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE platform_users ADD COLUMN IF NOT EXISTS organization_id UUID REFERENCES organizations(id) ON DELETE SET NULL;
        ALTER TABLE platform_users ADD COLUMN IF NOT EXISTS role VARCHAR(64) NOT NULL DEFAULT 'member';

        CREATE INDEX IF NOT EXISTS ix_platform_users_organization_id ON platform_users (organization_id);
        CREATE INDEX IF NOT EXISTS ix_platform_users_role ON platform_users (role);

        -- Seed initial superadmins with superadmin role and default organization
        UPDATE platform_users
        SET role = 'superadmin', organization_id = '00000000-0000-0000-0000-000000000001'
        WHERE is_superuser = true;

        -- Associate standard users with default organization
        UPDATE platform_users
        SET organization_id = '00000000-0000-0000-0000-000000000001'
        WHERE organization_id IS NULL AND is_superuser = false;
        """
    )

    # ------------------------------------------------------------------
    # 4. Reusable attach_audit_trigger migration helper
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION attach_audit_trigger(target_table TEXT) RETURNS VOID AS $$
        DECLARE
            trg_name TEXT := 'trg_audit_' || target_table;
        BEGIN
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I;', trg_name, target_table);
            EXECUTE format(
                'CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I ' ||
                'FOR EACH ROW EXECUTE FUNCTION process_audit_log();',
                trg_name, target_table
            );
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS attach_audit_trigger(TEXT);")
    op.execute(
        """
        DROP INDEX IF EXISTS ix_platform_users_role;
        DROP INDEX IF EXISTS ix_platform_users_organization_id;
        ALTER TABLE platform_users DROP COLUMN IF EXISTS role;
        ALTER TABLE platform_users DROP COLUMN IF EXISTS organization_id;
        DROP TABLE IF EXISTS organizations CASCADE;
        """
    )
