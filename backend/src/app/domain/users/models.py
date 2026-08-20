"""
User domain model — production-hardened with GIN tri-gram indexes.

GIN indexes with gin_trgm_ops allow PostgreSQL to execute
``LIKE '%fragment%'``, ``ILIKE '%fragment%'``, and ``%`` (pg_trgm similarity)
queries efficiently — essential for admin user-search UIs.

Note: the ``pg_trgm`` extension must exist before migration runs.
Migration 0001 already provisions it via
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')
"""
from sqlalchemy import Boolean, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import AuditBase


class User(AuditBase):
    __tablename__ = "platform_users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,       # standard B-Tree index for equality / join lookups
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))

    __table_args__ = (
        # GIN + gin_trgm_ops — supports ILIKE / LIKE / similarity on email
        # Used by admin search:  WHERE email % :query  or  ILIKE '%fragment%'
        Index(
            "ix_platform_users_email_trgm",
            "email",
            postgresql_using="gin",
            postgresql_ops={"email": "gin_trgm_ops"},
        ),
        # GIN + gin_trgm_ops on full_name for fast fuzzy name search
        Index(
            "ix_platform_users_full_name_trgm",
            "full_name",
            postgresql_using="gin",
            postgresql_ops={"full_name": "gin_trgm_ops"},
        ),
    )
