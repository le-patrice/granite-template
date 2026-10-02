"""
Transactional Outbox Event Relay and Dead Letter Queue (DLQ) dispatcher.

Reads pending events from PostgreSQL `outbox_events`, dispatches to Valkey
streams/pubsub, and quarantines persistent failures into `dead_letter_events`.
"""

from __future__ import annotations

import asyncio
import traceback
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.domain.events.contracts import IOutboxRepository
from app.domain.events.models import DeadLetterEvent, OutboxEvent, OutboxStatus

logger = structlog.get_logger()


class PostgresOutboxRepository(IOutboxRepository):
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_event(self, event_type: str, payload_json: str) -> OutboxEvent:
        event = OutboxEvent(
            event_type=event_type,
            payload_json=payload_json,
            status=OutboxStatus.PENDING,
        )
        self.session.add(event)
        await self.session.commit()
        return event

    async def get_pending_events(self, limit: int = 50) -> list[OutboxEvent]:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status.in_([OutboxStatus.PENDING, OutboxStatus.FAILED]))
            .where(OutboxEvent.retry_count < 3)
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def mark_processed(self, event_id: uuid.UUID) -> None:
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status=OutboxStatus.PROCESSED,
                processed_at=datetime.now(UTC),
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def record_failure(
        self, event_id: uuid.UUID, error_trace: str, max_retries: int = 3
    ) -> None:
        stmt = select(OutboxEvent).where(OutboxEvent.id == event_id)
        res = await self.session.execute(stmt)
        event = res.scalar_one_or_none()
        if not event:
            return

        event.retry_count += 1
        if event.retry_count >= max_retries:
            event.status = OutboxStatus.DEAD_LETTER
            # Insert into DLQ
            dlq_item = DeadLetterEvent(
                original_event_id=event.id,
                event_type=event.event_type,
                payload_json=event.payload_json,
                error_trace=error_trace,
            )
            self.session.add(dlq_item)
            logger.error(
                "outbox.quarantined_to_dlq",
                event_id=str(event.id),
                event_type=event.event_type,
                retry_count=event.retry_count,
            )
        else:
            event.status = OutboxStatus.FAILED
            logger.warning(
                "outbox.retry_scheduled",
                event_id=str(event.id),
                event_type=event.event_type,
                retry_count=event.retry_count,
            )

        await self.session.commit()

    async def get_dead_letters(self, limit: int = 50) -> list[DeadLetterEvent]:
        stmt = select(DeadLetterEvent).order_by(DeadLetterEvent.failed_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def replay_dead_letter(self, dead_letter_id: uuid.UUID) -> OutboxEvent | None:
        stmt = select(DeadLetterEvent).where(DeadLetterEvent.id == dead_letter_id)
        res = await self.session.execute(stmt)
        dlq_item = res.scalar_one_or_none()
        if not dlq_item:
            return None

        # Reset original outbox event or create fresh outbox event
        outbox_stmt = select(OutboxEvent).where(OutboxEvent.id == dlq_item.original_event_id)
        outbox_res = await self.session.execute(outbox_stmt)
        outbox_event = outbox_res.scalar_one_or_none()

        if outbox_event:
            outbox_event.status = OutboxStatus.PENDING
            outbox_event.retry_count = 0
        else:
            outbox_event = OutboxEvent(
                event_type=dlq_item.event_type,
                payload_json=dlq_item.payload_json,
                status=OutboxStatus.PENDING,
            )
            self.session.add(outbox_event)

        await self.session.delete(dlq_item)
        await self.session.commit()
        logger.info("outbox.dlq_replayed", dead_letter_id=str(dead_letter_id))
        return outbox_event


class OutboxRelay:
    """Dispatches pending outbox events to Valkey pubsub / streams."""

    def __init__(self, repo: IOutboxRepository) -> None:
        self.repo = repo

    async def publish_event(self, event: OutboxEvent) -> None:
        from app.core.cache import get_valkey_pool

        v_client = get_valkey_pool()
        channel = f"events:{event.event_type}"
        await v_client.publish(channel, event.payload_json)
        logger.info("outbox.published", event_id=str(event.id), channel=channel)

    async def process_sweep(self, batch_size: int = 50) -> int:
        events = await self.repo.get_pending_events(limit=batch_size)
        if not events:
            return 0

        processed = 0
        for event in events:
            try:
                await self.publish_event(event)
                await self.repo.mark_processed(event.id)
                processed += 1
            except Exception as exc:  # noqa: BLE001
                tb = traceback.format_exc()
                logger.error("outbox.publish_failed", event_id=str(event.id), error=str(exc))
                await self.repo.record_failure(event.id, error_trace=tb)

        return processed

    @staticmethod
    async def ensure_notify_trigger(session: AsyncSession) -> None:
        """Configures PostgreSQL trigger to notify on outbox inserts."""
        from sqlalchemy import text

        trigger_ddl = text("""
            CREATE OR REPLACE FUNCTION notify_outbox_event()
            RETURNS trigger AS $$
            BEGIN
                PERFORM pg_notify('outbox_events_channel', NEW.id::text);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_notify_outbox_event'
                ) THEN
                    CREATE TRIGGER trg_notify_outbox_event
                    AFTER INSERT ON outbox_events
                    FOR EACH ROW EXECUTE FUNCTION notify_outbox_event();
                END IF;
            END $$;
        """)
        await session.execute(trigger_ddl)
        await session.commit()
        logger.info("outbox.notify_trigger_verified")

    async def listen_and_relay(
        self,
        channel_name: str = "outbox_events_channel",
        sweep_interval_seconds: int = 15,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """
        Event-driven PostgreSQL LISTEN/NOTIFY daemon with safety-net periodic sweeps.
        Initializes a dedicated stateful asyncpg connection bypassing PgBouncer transaction
        pooling to guarantee unbroken session listening and sub-2ms event propagation.
        """
        import asyncpg

        event_queue: asyncio.Queue[str] = asyncio.Queue()

        def _on_notify(conn: Any, pid: int, channel: str, payload: str) -> None:
            event_queue.put_nowait(payload)

        # Connect directly to PostgreSQL (port 5432) bypassing PgBouncer transaction pooling (6432)
        direct_url = settings.direct_db_url
        if direct_url.startswith("postgresql+asyncpg://"):
            direct_url = direct_url.replace("postgresql+asyncpg://", "postgresql://", 1)

        direct_conn = await asyncpg.connect(direct_url)
        logger.info("outbox.dedicated_connection_established", target="postgres:5432")

        try:
            # Ensure the trigger exists in the database
            await direct_conn.execute("""
                CREATE OR REPLACE FUNCTION notify_outbox_event()
                RETURNS trigger AS $$
                BEGIN
                    PERFORM pg_notify('outbox_events_channel', NEW.id::text);
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_notify_outbox_event'
                    ) THEN
                        CREATE TRIGGER trg_notify_outbox_event
                        AFTER INSERT ON outbox_events
                        FOR EACH ROW EXECUTE FUNCTION notify_outbox_event();
                    END IF;
                END $$;
            """)

            await direct_conn.add_listener(channel_name, _on_notify)
            logger.info("outbox.listener_active", channel=channel_name)

            while stop_event is None or not stop_event.is_set():
                try:
                    # Wait for epoll notification with timeout for safety sweep
                    payload = await asyncio.wait_for(
                        event_queue.get(),
                        timeout=sweep_interval_seconds,
                    )
                    logger.debug("outbox.notify_received", event_id=payload)
                    # Drain any pending events immediately
                    await self.process_sweep(batch_size=100)
                except TimeoutError:
                    # Safety net sweep drains retries or missed signals
                    await self.process_sweep(batch_size=50)
        finally:
            try:
                await direct_conn.remove_listener(channel_name, _on_notify)
                await direct_conn.close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("outbox.listener_cleanup_error", error=str(exc))
            logger.info("outbox.listener_stopped")
