"""
Enterprise Governance, RLS, OCC, and TimescaleDB Audit CDC Integration Tests.

Tests:
1. PgBouncer-safe PostgreSQL session context listener (app.current_user_id, app.current_tenant_id, app.current_role).
2. Optimistic Concurrency Control (OCC) detecting conflicting concurrent updates (StaleDataError).
3. TimescaleDB Immutable Audit CDC capturing JSONB diffs in audit_logs on entity mutations.
4. Transactional Outbox aggregate tracking and SAQ worker polling loop.
"""

from __future__ import annotations

import os
import uuid

import pytest
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException
from sqlalchemy import String, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm.exc import StaleDataError

from app.core.csrf import CSRFOriginMiddleware
from app.core.database import current_tenant_id, tenant_session, unit_of_work
from app.core.worker import poll_and_dispatch_outbox
from app.domain.base import TenantBase
from app.domain.events.models import OutboxEvent, OutboxStatus
from app.domain.users.models import User
from app.presentation.guards.auth_guard import tenant_required_guard


def _runtime_role_url() -> str:
    """Connection URL for the unprivileged app_runtime role on the same database as the app."""
    base = os.environ.get("DIRECT_DATABASE_URL") or os.environ.get(
        "DATABASE_URL",
        settings.direct_db_url,
    )
    return (
        make_url(base)
        .set(
            username="app_runtime",
            password=os.environ.get("APP_RUNTIME_PASSWORD", "secure_dev_password"),
        )
        .render_as_string(hide_password=False)
    )


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


@pytest.mark.asyncio
class TestMultiTenantIsolationAndSession:
    async def test_tenant_session_context_manager(self, db_session: AsyncSession):
        tenant_id = uuid.uuid4()
        user_id = uuid.uuid4()

        assert current_tenant_id.get() == ""

        async with tenant_session(
            tenant_id, user_id=user_id, role="user", session=db_session
        ) as session:
            assert current_tenant_id.get() == str(tenant_id)
            assert session.info["tenant_id"] == str(tenant_id)
            assert session.info["user_id"] == str(user_id)

            # Query should verify set_config applied
            res = await session.execute(
                text(
                    "SELECT current_setting('app.current_user_id', true), "
                    "current_setting('app.current_tenant_id', true), "
                    "current_setting('app.current_role', true)"
                )
            )
            row = res.fetchone()
            assert row is not None
            assert row[0] == str(user_id)
            assert row[1] == str(tenant_id)
            assert row[2] == "user"

        # Contextvars must be completely reset after block
        assert current_tenant_id.get() == ""

    async def test_tenant_required_guard_blocks_empty_tenant(self):
        class DummyConn:
            def __init__(self, user_id=None, tenant_id=None, is_super=False, role="user"):
                self.scope = {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "is_superuser": is_super,
                    "role": role,
                }

        # 1. Unauthenticated -> NotAuthorizedException
        with pytest.raises(NotAuthorizedException):
            tenant_required_guard(DummyConn(), None)

        # 2. Authenticated user without tenant -> PermissionDeniedException
        conn_no_tenant = DummyConn(user_id="user-123", tenant_id="")
        with pytest.raises(PermissionDeniedException) as exc:
            tenant_required_guard(conn_no_tenant, None)
        assert "Multi-tenant context required" in str(exc.value)

        # 3. Authenticated user with tenant -> passes
        conn_with_tenant = DummyConn(user_id="user-123", tenant_id=str(uuid.uuid4()))
        tenant_required_guard(conn_with_tenant, None)

        # 4. Superuser without tenant -> passes
        conn_super = DummyConn(user_id="admin-123", tenant_id="", is_super=True, role="superadmin")
        tenant_required_guard(conn_super, None)


@pytest.mark.asyncio
class TestCSRFOriginSecurity:
    async def test_csrf_blocks_cross_site_cookie_post(self):
        called = False

        async def dummy_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = CSRFOriginMiddleware(dummy_app)

        received_events = []

        async def send(event):
            received_events.append(event)

        # Cookie present, state-changing POST, cross-site header
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/resource",
            "headers": [
                (b"cookie", b"access_token=secret_jwt"),
                (b"sec-fetch-site", b"cross-site"),
                (b"origin", b"http://attacker.com"),
            ],
        }

        await middleware(scope, None, send)
        assert not called
        assert len(received_events) > 0
        assert received_events[0]["status"] == 403

    async def test_csrf_allows_same_origin_cookie_post(self):
        called = False

        async def dummy_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = CSRFOriginMiddleware(dummy_app)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/resource",
            "headers": [
                (b"cookie", b"access_token=secret_jwt"),
                (b"origin", b"http://localhost:8000"),
                (b"host", b"localhost:8000"),
            ],
        }

        await middleware(scope, None, lambda event: None)
        assert called

    async def test_csrf_exempts_bearer_auth_without_cookie(self):
        called = False

        async def dummy_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = CSRFOriginMiddleware(dummy_app)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/resource",
            "headers": [
                (b"authorization", b"Bearer some_token"),
                (b"origin", b"http://external-partner.com"),
            ],
        }

        await middleware(scope, None, lambda event: None)
        assert called

    async def test_csrf_blocks_cookie_post_missing_both_origin_and_referer(self):
        called = False

        async def dummy_app(scope, receive, send):
            nonlocal called
            called = True

        middleware = CSRFOriginMiddleware(dummy_app)

        received_events = []

        async def send(event):
            received_events.append(event)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/resource",
            "headers": [
                (b"cookie", b"access_token=secret_jwt"),
                (b"host", b"api.example.com"),
            ],
        }

        await middleware(scope, None, send)
        assert not called
        assert len(received_events) > 0
        assert received_events[0]["status"] == 403


@pytest.mark.asyncio
class TestNonSuperuserRLSIsolation:
    async def test_non_superuser_runtime_role_enforces_rls_isolation(self, async_engine):
        """
        Validates that connecting as the non-superuser 'app_runtime' role (NOSUPERUSER, NOBYPASSRLS)
        strictly enforces Row-Level Security: Tenant B cannot read rows created by Tenant A.
        """
        runtime_url = _runtime_role_url()
        runtime_engine = create_async_engine(runtime_url)

        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        record_id = uuid.uuid4()

        try:
            # 1. Insert row under Tenant A context using app_runtime
            async with AsyncSession(runtime_engine, expire_on_commit=False) as session_a:
                session_a.info["tenant_id"] = str(tenant_a)
                session_a.info["role"] = "user"
                await session_a.execute(
                    text(
                        "INSERT INTO audit_logs (id, table_name, operation, record_id, organization_id, created_at) "
                        "VALUES (:id, 'orders', 'INSERT', :rec_id, :org_id, now())"
                    ),
                    {"id": uuid.uuid4(), "rec_id": record_id, "org_id": tenant_a},
                )
                await session_a.commit()

            # 2. Query as Tenant B under app_runtime: MUST RETURN 0 ROWS
            async with AsyncSession(runtime_engine, expire_on_commit=False) as session_b:
                session_b.info["tenant_id"] = str(tenant_b)
                session_b.info["role"] = "user"
                res = await session_b.execute(
                    text("SELECT count(*) FROM audit_logs WHERE record_id = :rec_id"),
                    {"rec_id": record_id},
                )
                count = res.scalar()
                assert count == 0, "RLS Breach: Tenant B was able to read Tenant A audit log row!"

            # 3. Query as Tenant A under app_runtime: MUST RETURN 1 ROW
            async with AsyncSession(runtime_engine, expire_on_commit=False) as session_a:
                session_a.info["tenant_id"] = str(tenant_a)
                session_a.info["role"] = "user"
                res = await session_a.execute(
                    text("SELECT count(*) FROM audit_logs WHERE record_id = :rec_id"),
                    {"rec_id": record_id},
                )
                count = res.scalar()
                assert count == 1, "Tenant A should see its own row under RLS"

            # 4. Query as Superadmin: BYPASS ALLOWS SEEING ROW
            async with AsyncSession(runtime_engine, expire_on_commit=False) as session_admin:
                session_admin.info["role"] = "superadmin"
                res = await session_admin.execute(
                    text("SELECT count(*) FROM audit_logs WHERE record_id = :rec_id"),
                    {"rec_id": record_id},
                )
                count = res.scalar()
                assert count == 1, "Superadmin should see all tenant rows"
        finally:
            await runtime_engine.dispose()


@pytest.mark.asyncio
class TestUnitOfWorkHelper:
    async def test_unit_of_work_commits_on_success(self, async_engine):
        user_id = uuid.uuid4()
        email = f"uow.{uuid.uuid4().hex[:8]}@example.com"

        async with (
            AsyncSession(async_engine, expire_on_commit=False) as s,
            unit_of_work(session=s) as session,
        ):
            user = User(
                id=user_id,
                email=email,
                hashed_password="hash",
                full_name="UoW User",
                is_active=True,
                is_superuser=False,
            )
            session.add(user)

        # Verify persisted
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            res = await session.execute(
                text("SELECT email FROM platform_users WHERE id = :id"),
                {"id": user_id},
            )
            assert res.scalar() == email

    async def test_unit_of_work_rolls_back_on_exception(self, async_engine):
        user_id = uuid.uuid4()
        email = f"uow.fail.{uuid.uuid4().hex[:8]}@example.com"

        with pytest.raises(RuntimeError):
            async with (
                AsyncSession(async_engine, expire_on_commit=False) as s,
                unit_of_work(session=s) as session,
            ):
                user = User(
                    id=user_id,
                    email=email,
                    hashed_password="hash",
                    full_name="UoW Fail User",
                    is_active=True,
                    is_superuser=False,
                )
                session.add(user)
                raise RuntimeError("Deliberate failure to test rollback")

        # Verify NOT persisted
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            res = await session.execute(
                text("SELECT count(*) FROM platform_users WHERE id = :id"),
                {"id": user_id},
            )
            assert res.scalar() == 0


@pytest.mark.asyncio
class TestStrictTenantRLSProcedure:
    async def test_attach_tenant_rls_strict_rejects_null_tenant(self, async_engine):
        runtime_url = _runtime_role_url()
        runtime_engine = create_async_engine(runtime_url)

        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()

        try:
            # 1. Setup table with attach_tenant_rls_strict
            async with AsyncSession(async_engine) as admin_s:
                await admin_s.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS test_strict_entities ("
                        "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                        "  name VARCHAR(128) NOT NULL,"
                        "  organization_id UUID"
                        ");"
                    )
                )
                await admin_s.execute(
                    text("SELECT attach_tenant_rls_strict('test_strict_entities');")
                )
                await admin_s.execute(
                    text(
                        "GRANT SELECT, INSERT, UPDATE, DELETE ON test_strict_entities TO app_runtime;"
                    )
                )
                await admin_s.commit()

            # 2. Insert row as Tenant A under app_runtime
            row_a_id = uuid.uuid4()
            async with AsyncSession(runtime_engine, expire_on_commit=False) as session_a:
                session_a.info["tenant_id"] = str(tenant_a)
                session_a.info["role"] = "user"
                await session_a.execute(
                    text(
                        "INSERT INTO test_strict_entities (id, name, organization_id) "
                        "VALUES (:id, 'Tenant A Item', :org_id)"
                    ),
                    {"id": row_a_id, "org_id": tenant_a},
                )
                await session_a.commit()

            # 3. Query as Tenant B under app_runtime: 0 rows
            async with AsyncSession(runtime_engine, expire_on_commit=False) as session_b:
                session_b.info["tenant_id"] = str(tenant_b)
                session_b.info["role"] = "user"
                res = await session_b.execute(
                    text("SELECT count(*) FROM test_strict_entities WHERE id = :id"),
                    {"id": row_a_id},
                )
                assert res.scalar() == 0

            # 4. Non-superadmin cannot see NULL-tenant rows under strict RLS
            null_row_id = uuid.uuid4()
            async with AsyncSession(async_engine) as admin_s:
                await admin_s.execute(
                    text(
                        "INSERT INTO test_strict_entities (id, name, organization_id) VALUES (:id, 'Orphan', NULL)"
                    ),
                    {"id": null_row_id},
                )
                await admin_s.commit()

            # Tenant A queries for the NULL-tenant row: MUST BE INVISIBLE (count == 0)
            async with AsyncSession(runtime_engine, expire_on_commit=False) as session_a:
                session_a.info["tenant_id"] = str(tenant_a)
                session_a.info["role"] = "user"
                res = await session_a.execute(
                    text("SELECT count(*) FROM test_strict_entities WHERE id = :id"),
                    {"id": null_row_id},
                )
                assert res.scalar() == 0, (
                    "Strict RLS breach: non-superadmin could read NULL-tenant row!"
                )
        finally:
            await runtime_engine.dispose()
