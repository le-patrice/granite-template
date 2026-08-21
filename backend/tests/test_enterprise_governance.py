"""
Enterprise Governance, RLS, OCC, and TimescaleDB Audit CDC Integration Tests.

Tests:
1. PgBouncer-safe PostgreSQL session context listener (app.current_user_id, app.current_tenant_id, app.current_role).
2. Optimistic Concurrency Control (OCC) detecting conflicting concurrent updates (StaleDataError).
3. TimescaleDB Immutable Audit CDC capturing JSONB diffs in audit_logs on entity mutations.
4. Transactional Outbox aggregate tracking and SAQ worker polling loop.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import String, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.exc import StaleDataError

from app.core.worker import poll_and_dispatch_outbox
from app.domain.base import TenantBase
from app.domain.events.models import OutboxEvent, OutboxStatus
from app.domain.users.models import User


# Generic tenant-scoped model inheriting from universal TenantBase
class SampleTenantEntity(TenantBase):
    __tablename__ = "test_tenant_entities"

    name: Mapped[str] = mapped_column(String(128), nullable=False)


@pytest.mark.asyncio
class TestRLSSessionContext:
    async def test_session_context_listener_sets_transaction_locals(self, db_session: AsyncSession):
        user_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        db_session.info["user_id"] = user_id
        db_session.info["tenant_id"] = tenant_id
        db_session.info["role"] = "superadmin"

        # Execute query; after_begin hook fires automatically
        result = await db_session.execute(
            text(
                "SELECT current_setting('app.current_user_id', true), "
                "current_setting('app.current_tenant_id', true), "
                "current_setting('app.current_role', true)"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == user_id
        assert row[1] == tenant_id
        assert row[2] == "superadmin"

    async def test_session_context_defaults_safely_when_empty(self, db_session: AsyncSession):
        db_session.info.clear()

        result = await db_session.execute(
            text(
                "SELECT current_setting('app.current_user_id', true), "
                "current_setting('app.current_tenant_id', true), "
                "current_setting('app.current_role', true)"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == ""
        assert row[1] == ""
        assert row[2] == "guest"


@pytest.mark.asyncio
class TestOptimisticConcurrencyControl:
    async def test_occ_version_conflict_raises_stale_data_error(self, async_engine):
        # Create table for SampleTenantEntity
        async with async_engine.begin() as conn:
            await conn.run_sync(SampleTenantEntity.metadata.create_all)

        org_id = uuid.uuid4()
        entity_id = uuid.uuid4()

        # Session 1 creates entity
        async with AsyncSession(async_engine, expire_on_commit=False) as s1:
            item = SampleTenantEntity(id=entity_id, organization_id=org_id, name="Initial Name")
            s1.add(item)
            await s1.commit()
            assert item.version_id == 1

        # Session 2 loads entity
        async with AsyncSession(async_engine, expire_on_commit=False) as s2:
            item2 = await s2.get(SampleTenantEntity, entity_id)
            assert item2 is not None

            # Concurrent update in Session 3 commits first
            async with AsyncSession(async_engine, expire_on_commit=False) as s3:
                item3 = await s3.get(SampleTenantEntity, entity_id)
                assert item3 is not None
                item3.name = "Updated by Session 3"
                await s3.commit()
                assert item3.version_id == 2

            # Session 2 tries to commit stale state (version_id=1) -> StaleDataError
            item2.name = "Conflicting Update by Session 2"
            with pytest.raises(StaleDataError):
                await s2.commit()


@pytest.mark.asyncio
class TestTimescaleDBAuditCDC:
    async def test_user_mutations_capture_audit_log_diffs(self, async_engine):
        admin_id = str(uuid.uuid4())
        target_user_id = uuid.uuid4()
        email = f"audited.{uuid.uuid4().hex[:8]}@example.com"

        # Insert user with admin context
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            session.info["user_id"] = admin_id
            session.info["role"] = "superadmin"

            user = User(
                id=target_user_id,
                email=email,
                hashed_password="hash",
                full_name="Audit Test User",
                is_active=True,
                is_superuser=False,
            )
            session.add(user)
            await session.commit()

        # Verify INSERT captured in audit_logs
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            res = await session.execute(
                text(
                    "SELECT table_name, operation, record_id, changed_by, new_data "
                    "FROM audit_logs WHERE record_id = :id ORDER BY created_at ASC"
                ),
                {"id": target_user_id},
            )
            rows = res.fetchall()
            assert len(rows) >= 1
            insert_log = rows[0]
            assert insert_log[0] == "platform_users"
            assert insert_log[1] == "INSERT"
            assert str(insert_log[2]) == str(target_user_id)
            assert insert_log[3] == admin_id
            assert insert_log[4]["email"] == email


@pytest.mark.asyncio
class TestOutboxWorkerLoop:
    async def test_outbox_event_with_aggregate_dispatches_cleanly(self, async_engine, monkeypatch):
        event_id = uuid.uuid4()
        agg_id = uuid.uuid4()

        # Mock valkey publish
        async def mock_publish(self, channel, message):
            return 1

        import valkey.asyncio as valkey
        monkeypatch.setattr(valkey.Valkey, "publish", mock_publish)

        # Enqueue event with aggregate metadata
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            event = OutboxEvent(
                id=event_id,
                aggregate_type="user",
                aggregate_id=agg_id,
                event_type="user.created",
                payload_json='{"user_id": "123"}',
                status=OutboxStatus.PENDING,
            )
            session.add(event)
            await session.commit()

        # Run SAQ background worker poller
        processed_count = await poll_and_dispatch_outbox(ctx={"job_id": "test_job"})
        assert processed_count >= 1

        # Verify status is now PROCESSED
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            res = await session.execute(
                text("SELECT status, processed_at FROM outbox_events WHERE id = :id"),
                {"id": event_id},
            )
            row = res.fetchone()
            assert row is not None
            assert row[0] == OutboxStatus.PROCESSED.value
            assert row[1] is not None
