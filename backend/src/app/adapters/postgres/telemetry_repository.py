"""
PostgreSQL bulk-insert adapter for telemetry ingestion.

Uses a single parameterised INSERT ... VALUES (...), (...), ...
statement instead of per-row ORM calls.  At 1 000 records/batch this
reduces DB round-trips by ~1 000×.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.telemetry.contracts import ITelemetryRepository
from app.domain.telemetry.schemas import TelemetryRecord


class PostgresTelemetryRepository(ITelemetryRepository):
    """
    Concrete telemetry repository using raw parameterised bulk SQL.

    We bypass the ORM mapper entirely for the write path because:
    •  ORM unit-of-work adds per-object overhead that matters at IoT scale.
    •  asyncpg can send executemany as a single prepared statement pipeline.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_batch(self, records: list[TelemetryRecord]) -> None:
        if not records:
            return

        now = datetime.now(timezone.utc)

        # Build a list of dicts matching the column names
        rows = [
            {
                "id": str(uuid.uuid4()),
                "transformer_id": r.transformer_id,
                "voltage_v": r.voltage_v,
                "current_a": r.current_a,
                "power_factor": r.power_factor,
                "frequency_hz": r.frequency_hz,
                # Convert Unix epoch float → UTC datetime
                "recorded_at": datetime.fromtimestamp(
                    r.timestamp_epoch, tz=timezone.utc
                ),
                "ingested_at": now,
            }
            for r in records
        ]

        # Single-statement bulk insert; asyncpg sends this as one server
        # round-trip regardless of batch size.
        stmt = text(
            """
            INSERT INTO telemetry_readings
                (id, transformer_id, voltage_v, current_a,
                 power_factor, frequency_hz, recorded_at, ingested_at)
            VALUES
                (:id, :transformer_id, :voltage_v, :current_a,
                 :power_factor, :frequency_hz, :recorded_at, :ingested_at)
            ON CONFLICT DO NOTHING
            """
        )

        await self.session.execute(stmt, rows)
        await self.session.commit()
