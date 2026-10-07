"""
msgspec struct schemas for Outbox and Dead Letter Queue events.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import msgspec


class OutboxEventCreate(msgspec.Struct, frozen=True, kw_only=True):
    event_type: str
    payload_json: str
    organization_id: uuid.UUID | None = None
    aggregate_type: str = "general"
    aggregate_id: uuid.UUID | None = None


class OutboxEventRead(msgspec.Struct, frozen=True, kw_only=True):
    id: uuid.UUID
    event_type: str
    payload_json: str
    status: str
    retry_count: int
    created_at: datetime
    organization_id: uuid.UUID | None = None
    aggregate_type: str = "general"
    aggregate_id: uuid.UUID | None = None
    processed_at: datetime | None = None


class DeadLetterEventRead(msgspec.Struct, frozen=True, kw_only=True):
    id: uuid.UUID
    original_event_id: uuid.UUID
    event_type: str
    payload_json: str
    error_trace: str
    failed_at: datetime
