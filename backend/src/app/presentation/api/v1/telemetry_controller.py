"""
Telemetry ingestion controller.

POST /api/v1/telemetry/ingest
    Accepts a list of TelemetryRecord objects (zero-copy msgspec
    validation), bulk-inserts to PostgreSQL, and fans out the latest
    reading per unique transformer to Valkey for hot-path cache.
"""
from litestar import Controller, post
from litestar.di import Provide
from litestar.status_codes import HTTP_202_ACCEPTED
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.cache import valkey_service
from app.adapters.postgres.telemetry_repository import PostgresTelemetryRepository
from app.domain.telemetry.contracts import ITelemetryRepository
from app.domain.telemetry.schemas import TelemetryRecord
from app.presentation.guards.auth_guard import JWTAuthGuard


# ---------------------------------------------------------------------------
# DI provider
# ---------------------------------------------------------------------------

async def provide_telemetry_repo(db_session: AsyncSession) -> ITelemetryRepository:
    return PostgresTelemetryRepository(session=db_session)


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

class TelemetryController(Controller):
    path = "/telemetry"
    guards = [JWTAuthGuard()]
    dependencies = {"telemetry_repo": Provide(provide_telemetry_repo)}

    @post(
        path="/ingest",
        status_code=HTTP_202_ACCEPTED,
        summary="Bulk telemetry ingestion",
        description=(
            "Accepts a list of TelemetryRecord objects. "
            "Records are bulk-inserted to PostgreSQL and the latest reading "
            "per unique transformer_id is written to Valkey."
        ),
    )
    async def ingest(
        self,
        data: list[TelemetryRecord],
        telemetry_repo: ITelemetryRepository,
    ) -> dict:
        # ── 1. Persist entire batch to PostgreSQL (one round-trip) ──────────
        await telemetry_repo.add_batch(data)

        # ── 2. Update Valkey with the latest reading per transformer ────────
        # Keep only the newest record per transformer_id so we never
        # overwrite a newer state with an older one that arrived out-of-order.
        latest: dict[str, TelemetryRecord] = {}
        for record in data:
            existing = latest.get(record.transformer_id)
            if existing is None or record.timestamp_epoch > existing.timestamp_epoch:
                latest[record.transformer_id] = record

        # Fan out concurrently – asyncio.gather avoids sequential awaits
        import asyncio
        await asyncio.gather(
            *(
                valkey_service.set_transformer_state(tid, rec)
                for tid, rec in latest.items()
            )
        )

        return {
            "accepted": len(data),
            "transformers_updated": len(latest),
        }
