"""
PostgreSQL bulk-insert adapter for telemetry ingestion.

Uses a single parameterised INSERT ... VALUES (...), (...), ...
statement instead of per-row ORM calls.  At 1 000 records/batch this
reduces DB round-trips by ~1 000×.
"""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.telemetry.contracts import ITelemetryRepository
from app.domain.telemetry.schemas import TelemetryRecord

logger = structlog.get_logger()


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

        now = datetime.now(UTC)

        # 1. Pre-allocate tuples for binary PostgreSQL CopyFrom protocol
        rows = [
            (
                uuid.uuid4(),
                r.transformer_id,
                r.voltage_v,
                r.current_a,
                r.power_factor,
                r.frequency_hz,
                datetime.fromtimestamp(r.timestamp_epoch, tz=UTC),
                now,
            )
            for r in records
        ]

        # 2. Fast-path: Binary COPY via asyncpg driver connection
        try:
            conn = await self.session.connection()
            raw_conn = await conn.get_raw_connection()
            driver = getattr(raw_conn, "driver_connection", None)
            if driver is not None and hasattr(driver, "copy_records_to_table"):
                await driver.copy_records_to_table(
                    "telemetry_readings",
                    records=rows,
                    columns=[
                        "id",
                        "transformer_id",
                        "voltage_v",
                        "current_a",
                        "power_factor",
                        "frequency_hz",
                        "recorded_at",
                        "ingested_at",
                    ],
                )
                await self.session.commit()
                return
        except (SQLAlchemyError, AttributeError, OSError, RuntimeError) as exc:
            # Fallback to standard parameterised insert if driver COPY is unavailable
            logger.debug(
                "Driver binary COPY unavailable or failed; using multi-row insert fallback",
                error=str(exc),
            )

        # 3. Fallback: single-statement bulk insert
        dict_rows = [
            {
                "id": str(r[0]),
                "transformer_id": r[1],
                "voltage_v": r[2],
                "current_a": r[3],
                "power_factor": r[4],
                "frequency_hz": r[5],
                "recorded_at": r[6],
                "ingested_at": r[7],
            }
            for r in rows
        ]
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

        await self.session.execute(stmt, dict_rows)
        await self.session.commit()
