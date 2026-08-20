"""
Transactional Outbox Event Relay and Dead Letter Queue (DLQ) dispatcher.

Reads pending events from PostgreSQL `outbox_events`, dispatches to Valkey
streams/pubsub, and quarantines persistent failures into `dead_letter_events`.
"""
from __future__ import annotations

import asyncio
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

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
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def mark_processed(self, event_id: uuid.UUID) -> None:
        stmt = (
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(
                status=OutboxStatus.PROCESSED,
                processed_at=datetime.now(timezone.utc),
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def record_failure(self, event_id: uuid.UUID, error_trace: str, max_retries: int = 3) -> None:
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
            logger.warn(
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
        import valkey.asyncio as valkey
        v_client = valkey.Valkey(
            host=settings.VALKEY_HOST,
            port=settings.VALKEY_PORT,
            socket_timeout=2.0,
        )
        try:
            channel = f"events:{event.event_type}"
            await v_client.publish(channel, event.payload_json)
            logger.info("outbox.published", event_id=str(event.id), channel=channel)
        finally:
            await v_client.aclose()

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
            except Exception as exc:
                tb = traceback.format_exc()
                logger.error("outbox.publish_failed", event_id=str(event.id), error=str(exc))
                await self.repo.record_failure(event.id, error_trace=tb)

        return processed
