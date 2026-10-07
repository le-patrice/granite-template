"""
Domain base classes with production-grade ORM features.

Features
--------
• ``AuditBase``: Abstract base entity with UUID PK and UTC audit timestamps.
• ``TenantBase``: Abstract base entity inheriting from ``AuditBase`` with
  tenant isolation (``organization_id``) and Optimistic Concurrency Control
  (``version_id`` + ``version_id_col`` mapping).
• ``VectorColumn``: Dialect-aware TypeDecorator adapted for pgvector embeddings.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any, ClassVar, Generic, TypeVar

import msgspec
from sqlalchemy import CheckConstraint, DateTime, Integer, func
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

__all__ = [
    "AuditBase",
    "Base",
    "PaginationEnvelope",
    "TenantBase",
    "VectorColumn",
    "enum_check_constraint",
]

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Audit mixin
# ---------------------------------------------------------------------------


class AuditBase(Base):
    """
    Abstract base entity with UUID PK and UTC audit timestamps.

    ``created_at`` and ``updated_at`` are set both at the Python layer
    (``default`` / ``onupdate``) and at the database layer
    (``server_default``), giving correctness whether the ORM or raw SQL
    performs the insert.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Tenant & OCC Base Mixin
# ---------------------------------------------------------------------------


class TenantBase(AuditBase):
    """
    Tenant-scoped base entity with PostgreSQL Row-Level Security (RLS) support
    and Optimistic Concurrency Control (OCC) version tracking.
    """

    __abstract__ = True

    organization_id: Mapped[uuid.UUID] = mapped_column(
        index=True,
        nullable=False,
    )
    version_id: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        nullable=False,
    )

    __mapper_args__: ClassVar[dict[str, Any]] = {"version_id_col": version_id}


# ---------------------------------------------------------------------------
# Dialect-aware vector column
# ---------------------------------------------------------------------------


class VectorColumn(TypeDecorator[list[float]]):
    """
    Fixed-dimension vector column compatible with pgvector on PostgreSQL.

    Resolution order at DDL / compile time:
      1. PostgreSQL  → ``pgvector.sqlalchemy.Vector(dim)``  (if pgvector installed)
      2. PostgreSQL  → ``JSON``                              (fallback, no pgvector)
      3. All others  → ``JSON``                              (cross-dialect)
    """

    impl = JSON
    cache_ok = True

    def __init__(self, dim: int) -> None:
        super().__init__()
        self.dim = dim

    @property
    def python_type(self) -> type[list[float]]:
        return list

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name in {"postgresql", "cockroachdb"}:
            try:
                from pgvector.sqlalchemy import Vector as PgVector  # type: ignore[import]

                return dialect.type_descriptor(PgVector(self.dim))
            except ImportError:
                # pgvector not installed — fall through to JSON
                pass
        return dialect.type_descriptor(JSON())

    def process_result_value(self, value: Any, dialect: Dialect) -> list[float] | None:
        if value is None:
            return None
        if hasattr(value, "tolist"):
            # numpy / pgvector ndarray
            return list(value.tolist())
        return list(value)


# ---------------------------------------------------------------------------
# Generic Pagination Envelope
# ---------------------------------------------------------------------------


class PaginationEnvelope(msgspec.Struct, Generic[T], frozen=True):
    """
    Standard generic pagination envelope across all domains.
    Guarantees consistent { items, total, limit, offset, pages } response structure.
    """

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def pages(self) -> int:
        if self.limit <= 0:
            return 1
        return (self.total + self.limit - 1) // self.limit


# ---------------------------------------------------------------------------
# Enum Database Check Constraint Helper
# ---------------------------------------------------------------------------


def enum_check_constraint(
    column_name: str,
    enum_cls: type[Enum],
    name: str | None = None,
) -> CheckConstraint:
    """
    Generates a SQLAlchemy CheckConstraint enforcing that `column_name`
    only contains valid string values from `enum_cls` directly in PostgreSQL DDL.
    """
    values = [f"'{e.value}'" for e in enum_cls]
    constraint_name = name or f"ck_{column_name}_enum"
    return CheckConstraint(f"{column_name} IN ({', '.join(values)})", name=constraint_name)
