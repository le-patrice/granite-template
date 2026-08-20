"""init_extensions_and_tables

Revision ID: 0001
Revises:
Create Date: 2026-08-20 00:00:00.000000 UTC

First migration:
  1. Enables required PostgreSQL extensions (uuid-ossp, pg_trgm, btree_gin, vector).
  2. Creates the platform_users table matching app.domain.users.models.User.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. PostgreSQL extensions
    # ------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "btree_gin";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')

    # ------------------------------------------------------------------
    # 2. platform_users table  (mirrors app.domain.users.models.User)
    # ------------------------------------------------------------------
    op.create_table(
        "platform_users",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # Unique constraint + index on email (mirrors index=True, unique=True on the model)
    op.create_index(
        "ix_platform_users_email",
        "platform_users",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("platform_users")
