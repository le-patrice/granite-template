"""
Comprehensive test suite for enterprise resilience layers:
- Three-Stage Health Probes
- Prometheus Metrics Endpoint
- Idempotency-Key Middleware
- Circuit Breaker State Machine
- Transactional Outbox & Dead Letter Queue (DLQ)
- Hybrid Search Reciprocal Rank Fusion (RRF)
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.outbox.relay import OutboxRelay, PostgresOutboxRepository
from app.core.circuit_breaker import CircuitBreaker, CircuitOpenException, CircuitState
from app.domain.events.models import OutboxStatus

# ---------------------------------------------------------------------------
# 1. Three-Stage Health Probes Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHealthProbes:
    async def test_liveness_probe(self, async_client: AsyncClient):
        resp = await async_client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "alive"}

    async def test_readiness_probe(self, async_client: AsyncClient):
        resp = await async_client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert "database" in data["dependencies"]

    async def test_startup_probe(self, async_client: AsyncClient):
        resp = await async_client.get("/health/startup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert "schema_version" in data


# ---------------------------------------------------------------------------
# 2. Prometheus Metrics Endpoint Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMetricsEndpoint:
    async def test_metrics_endpoint_returns_prometheus_format(self, async_client: AsyncClient):
        resp = await async_client.get("/metrics")
        assert resp.status_code == 200
        assert "text/plain" in resp.headers.get("content-type", "")
        body = resp.text
        assert "process_cpu_seconds_total" in body or "python_gc_objects_collected_total" in body


# ---------------------------------------------------------------------------
# 3. Circuit Breaker State Machine Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCircuitBreaker:
    async def test_circuit_breaker_transitions(self):
        cb = CircuitBreaker(
            name="test_service",
            failure_threshold=2,
            recovery_timeout=0.2,
            half_open_max_trials=1,
        )

        assert cb.state == CircuitState.CLOSED

        async def failing_call():
            raise ValueError("Upstream failure")

        # Failure 1
        with pytest.raises(ValueError):
            await cb.call(failing_call)
        assert cb.state == CircuitState.CLOSED

        # Failure 2 (trips circuit)
        with pytest.raises(ValueError):
            await cb.call(failing_call)
        assert cb.state == CircuitState.OPEN

        # Immediately rejected while OPEN
        with pytest.raises(CircuitOpenException):
            await cb.call(failing_call)

        # Wait for recovery timeout
        await asyncio.sleep(0.25)

        # Next call transitions to HALF_OPEN
        async def succeeding_call():
            return "recovered"

        result = await cb.call(succeeding_call)
        assert result == "recovered"
        assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# 4. Idempotency Key Middleware Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIdempotency:
    async def test_idempotent_duplicate_request(self, async_client: AsyncClient):
        key = f"test-idemp-{uuid.uuid4().hex}"
        email = f"idemp.{uuid.uuid4().hex[:8]}@example.com"
        payload = {
            "email": email,
            "password": "SecurePassword123!",
            "full_name": "Idempotent Tester",
        }

        # 1st request
        resp1 = await async_client.post(
            "/api/v1/users/register",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        assert resp1.status_code == 201
        data1 = resp1.json()

        # 2nd request with exact same Idempotency-Key
        resp2 = await async_client.post(
            "/api/v1/users/register",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        assert resp2.status_code == 201
        data2 = resp2.json()

        assert data1["id"] == data2["id"]
        assert data1["email"] == data2["email"]


# ---------------------------------------------------------------------------
# 5. Transactional Outbox & DLQ Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTransactionalOutbox:
    async def test_outbox_lifecycle_and_dlq(self, db_session: AsyncSession):
        repo = PostgresOutboxRepository(db_session)
        OutboxRelay(repo)

        # 1. Create outbox event
        event = await repo.create_event(
            event_type="order.completed",
            payload_json='{"order_id": "ORD-999", "amount": 149.99}',
        )
        assert event.id is not None
        assert event.status == OutboxStatus.PENDING

        # 2. Sweep events
        pending = await repo.get_pending_events()
        assert any(e.id == event.id for e in pending)

        # 3. Simulate failure progression to DLQ
        await repo.record_failure(event.id, error_trace="ConnectionTimeout", max_retries=2)
        await repo.record_failure(event.id, error_trace="ConnectionTimeout", max_retries=2)

        dead_letters = await repo.get_dead_letters()
        assert any(dl.original_event_id == event.id for dl in dead_letters)

        # 4. Replay from DLQ
        target_dl = next(dl for dl in dead_letters if dl.original_event_id == event.id)
        replayed = await repo.replay_dead_letter(target_dl.id)
        assert replayed is not None
        assert replayed.status == OutboxStatus.PENDING


# ---------------------------------------------------------------------------
# 6. Sliding-Window Rate Limiter Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSlidingWindowRateLimiter:
    async def test_auth_login_rate_limiting_triggers_429(self, async_client: AsyncClient):
        responses = []
        payload = {"email": "ratelimit.test@example.com", "password": "WrongPassword123!"}
        for _ in range(6):
            resp = await async_client.post("/api/v1/auth/login", json=payload)
            responses.append(resp)

        # First 5 should not be rate-limited (401 for wrong credentials)
        for resp in responses[:5]:
            assert resp.status_code != 429
            assert "ratelimit-limit" in resp.headers or "RateLimit-Limit" in resp.headers

        # 6th attempt should be throttled with 429 Too Many Requests
        sixth = responses[5]
        assert sixth.status_code == 429
        assert sixth.json().get("error") == "Too Many Requests"
        assert "Retry-After" in sixth.headers or "retry-after" in sixth.headers
        assert "RateLimit-Limit" in sixth.headers or "ratelimit-limit" in sixth.headers
        assert (
            sixth.headers.get("RateLimit-Remaining") == "0"
            or sixth.headers.get("ratelimit-remaining") == "0"
        )
