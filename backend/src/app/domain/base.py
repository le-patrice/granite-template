"""
Domain base classes with production-grade ORM features.

Changes vs. original
---------------------
• ``VectorColumn`` helper — a dialect-aware TypeDecorator adapted directly from
  ``references/advanced-alchemy/advanced_alchemy/types/vector.py`` so models can
  add ML embedding columns without importing advanced-alchemy types at runtime.
  Falls back to JSON on non-PostgreSQL dialects; uses ``pgvector.sqlalchemy.Vector``
  when the library is installed.

• ``AuditBase`` now uses ``server_default=func.now()`` for ``created_at`` /
  ``updated_at`` so TimescaleDB chunk compression doesn't trip on Python-side
  defaults.  ``onupdate`` is preserved for ORM-layer updates.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import DateTime, func
from sqlalchemy.engine import Dialect
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = ["Base", "AuditBase", "VectorColumn"]


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
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


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

    Adapted from:
      references/advanced-alchemy/advanced_alchemy/types/vector.py

    Usage in a model::

        class MyModel(AuditBase):
            embedding: Mapped[list[float]] = mapped_column(
                VectorColumn(1536), nullable=True
            )

    Similarity search (requires pgvector)::

        from sqlalchemy import select
        results = await session.execute(
            select(MyModel)
            .order_by(MyModel.embedding.cosine_distance([0.1, 0.2, ...]))
            .limit(10)
        )

    Notes
    -----
    •  ``cache_ok = True`` — the column is parameterised only by ``dim``,
       which is hashable, so SQLAlchemy can cache compiled statements.
    •  Import of ``pgvector`` is deferred to ``load_dialect_impl`` so the
       package is optional — models compile even without it installed.
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

    def process_result_value(
        self, value: Any, dialect: Dialect
    ) -> Optional[list[float]]:
        if value is None:
            return None
        if hasattr(value, "tolist"):
            # numpy / pgvector ndarray
            return list(value.tolist())
        return list(value)
