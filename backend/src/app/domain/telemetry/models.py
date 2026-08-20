"""
TelemetryReading SQLAlchemy entity.

TimescaleDB will automatically convert this table into a hypertable
(see migration) partitioned on `recorded_at` for time-series compression
and efficient range queries.

Composite index on (transformer_id, recorded_at) supports the two most
common query patterns:
  • "latest N readings for transformer X"
  • "all readings for transformer X in time-window [t0, t1]"
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.base import Base


class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"

    # Surrogate primary key – TimescaleDB hypertables work best with a
    # (id, time) composite PK, but a simple UUID is fine for now.
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    transformer_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Electrical measurements
    voltage_v: Mapped[float] = mapped_column(Float, nullable=False)
    current_a: Mapped[float] = mapped_column(Float, nullable=False)
    power_factor: Mapped[float] = mapped_column(Float, nullable=False)
    frequency_hz: Mapped[float] = mapped_column(Float, nullable=False)

    # Wall-clock time of the physical measurement (UTC, timezone-aware)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # Row insertion time – useful for lag monitoring
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Composite index: covers queries like
    #   WHERE transformer_id = :id AND recorded_at BETWEEN :t0 AND :t1
    # TimescaleDB will further prune partitions on `recorded_at`.
    __table_args__ = (
        Index("ix_telemetry_transformer_recorded", "transformer_id", "recorded_at"),
    )
