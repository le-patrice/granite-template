"""
Domain contracts for Outbox and Event Dispatching.
"""

from __future__ import annotations

import uuid
from typing import Protocol

from app.domain.events.models import DeadLetterEvent, OutboxEvent


class IOutboxRepository(Protocol):
    async def create_event(
        self,
        event_type: str,
        payload_json: str,
        *,
        organization_id: uuid.UUID | None = None,
        aggregate_type: str = "general",
        aggregate_id: uuid.UUID | None = None,
    ) -> OutboxEvent: ...

    async def get_pending_events(self, limit: int = 50) -> list[OutboxEvent]: ...

    async def mark_processed(self, event_id: uuid.UUID) -> None: ...

    async def record_failure(
        self, event_id: uuid.UUID, error_trace: str, max_retries: int = 3
    ) -> None: ...

    async def get_dead_letters(self, limit: int = 50) -> list[DeadLetterEvent]: ...

    async def replay_dead_letter(self, dead_letter_id: uuid.UUID) -> OutboxEvent | None: ...
