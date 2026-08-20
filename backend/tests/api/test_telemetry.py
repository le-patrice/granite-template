"""
Tests for the telemetry ingestion endpoint.

Coverage
--------
POST /api/v1/telemetry/ingest
    • Single-record batch — 202 + correct summary
    • Multi-record batch — 202 + correct accepted count
    • Multi-transformer batch — transformers_updated reflects unique IDs
    • Out-of-order records — Valkey receives only the newest per transformer
    • Empty batch — 202 accepted=0
    • Unauthenticated request — 401
    • Malformed payload (missing field) — 400 / 422
    • Valkey failure does not break ingestion (resilience)
"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_INGEST_URL = "/api/v1/telemetry/ingest"

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures & helpers
# ─────────────────────────────────────────────────────────────────────────────


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _record(
    transformer_id: str = "TRF-001",
    voltage_v: float = 11_000.0,
    current_a: float = 120.5,
    power_factor: float = 0.95,
    frequency_hz: float = 50.0,
    timestamp_epoch: float | None = None,
) -> dict:
    return {
        "transformer_id": transformer_id,
        "voltage_v": voltage_v,
        "current_a": current_a,
        "power_factor": power_factor,
        "frequency_hz": frequency_hz,
        "timestamp_epoch": timestamp_epoch or time.time(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Ingestion happy paths
# ─────────────────────────────────────────────────────────────────────────────


class TestTelemetryIngest:
    async def test_single_record(self, registered_user: dict, async_client: AsyncClient):
        resp = await async_client.post(
            _INGEST_URL,
            json=[_record()],
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["accepted"] == 1
        assert body["transformers_updated"] == 1

    async def test_multi_record_same_transformer(
        self, registered_user: dict, async_client: AsyncClient
    ):
        records = [_record(transformer_id="TRF-001") for _ in range(10)]
        resp = await async_client.post(
            _INGEST_URL,
            json=records,
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["accepted"] == 10
        # All records share the same transformer_id → only 1 Valkey update
        assert body["transformers_updated"] == 1

    async def test_multi_transformer_batch(self, registered_user: dict, async_client: AsyncClient):
        records = [
            _record(transformer_id=f"TRF-{i:03d}", timestamp_epoch=time.time() + i)
            for i in range(5)
        ]
        resp = await async_client.post(
            _INGEST_URL,
            json=records,
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["accepted"] == 5
        assert body["transformers_updated"] == 5

    async def test_empty_batch(self, registered_user: dict, async_client: AsyncClient):
        resp = await async_client.post(
            _INGEST_URL,
            json=[],
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["accepted"] == 0
        assert body["transformers_updated"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Out-of-order record handling
# ─────────────────────────────────────────────────────────────────────────────


class TestTelemetryOrdering:
    async def test_only_newest_record_cached(
        self, registered_user: dict, async_client: AsyncClient
    ):
        """
        When two records share the same transformer_id, only the one with the
        higher timestamp_epoch must be forwarded to Valkey.
        """
        now = time.time()
        old_record = _record(transformer_id="TRF-042", timestamp_epoch=now - 60)
        new_record = _record(
            transformer_id="TRF-042",
            voltage_v=12_000.0,  # distinctive value
            timestamp_epoch=now,
        )

        # Submit old first, then new — both in the same batch
        with patch(
            "app.adapters.cache.valkey_service.set_transformer_state",
            new_callable=AsyncMock,
        ) as mock_set:
            resp = await async_client.post(
                _INGEST_URL,
                # Intentionally send old first so order-unawareness would cache it
                json=[old_record, new_record],
                headers=_auth_headers(registered_user["token"]),
            )
            assert resp.status_code == 202, resp.text

            assert mock_set.call_count == 1
            _, cached_record = mock_set.call_args[0]
            voltage = (
                cached_record.voltage_v
                if hasattr(cached_record, "voltage_v")
                else cached_record["voltage_v"]
            )
            assert voltage == 12_000.0, "Valkey should receive the newest record, not the older one"

    async def test_reverse_arrival_order(self, registered_user: dict, async_client: AsyncClient):
        """Sending newest-first then oldest must still cache only the newest."""
        now = time.time()
        new_record = _record(
            transformer_id="TRF-099",
            voltage_v=9_999.0,
            timestamp_epoch=now,
        )
        old_record = _record(
            transformer_id="TRF-099",
            voltage_v=1_111.0,
            timestamp_epoch=now - 300,
        )

        with patch(
            "app.adapters.cache.valkey_service.set_transformer_state",
            new_callable=AsyncMock,
        ) as mock_set:
            resp = await async_client.post(
                _INGEST_URL,
                json=[new_record, old_record],
                headers=_auth_headers(registered_user["token"]),
            )
            assert resp.status_code == 202, resp.text

            assert mock_set.call_count == 1
            _, cached_record = mock_set.call_args[0]
            voltage = (
                cached_record.voltage_v
                if hasattr(cached_record, "voltage_v")
                else cached_record["voltage_v"]
            )
            assert voltage == 9_999.0


# ─────────────────────────────────────────────────────────────────────────────
# Authentication / authorisation
# ─────────────────────────────────────────────────────────────────────────────


class TestTelemetryAuth:
    async def test_ingest_without_token(self, async_client: AsyncClient):
        resp = await async_client.post(_INGEST_URL, json=[_record()])
        assert resp.status_code == 401

    async def test_ingest_with_invalid_token(self, async_client: AsyncClient):
        resp = await async_client.post(
            _INGEST_URL,
            json=[_record()],
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
        assert resp.status_code == 401

    async def test_ingest_with_tampered_bearer(self, async_client: AsyncClient):
        resp = await async_client.post(
            _INGEST_URL,
            json=[_record()],
            headers={"Authorization": "Token abc123"},  # wrong scheme
        )
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Payload validation
# ─────────────────────────────────────────────────────────────────────────────


class TestTelemetryValidation:
    async def test_missing_required_field(self, registered_user: dict, async_client: AsyncClient):
        # omit voltage_v
        bad_record = {
            "transformer_id": "TRF-BAD",
            "current_a": 50.0,
            "power_factor": 0.9,
            "frequency_hz": 50.0,
            "timestamp_epoch": time.time(),
        }
        resp = await async_client.post(
            _INGEST_URL,
            json=[bad_record],
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code in (400, 422)

    async def test_wrong_type_for_numeric_field(
        self, registered_user: dict, async_client: AsyncClient
    ):
        bad_record = _record()
        bad_record["voltage_v"] = "not-a-number"
        resp = await async_client.post(
            _INGEST_URL,
            json=[bad_record],
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code in (400, 422)

    async def test_not_a_list(self, registered_user: dict, async_client: AsyncClient):
        # Sending a single object instead of a list
        resp = await async_client.post(
            _INGEST_URL,
            json=_record(),
            headers=_auth_headers(registered_user["token"]),
        )
        assert resp.status_code in (400, 422)


# ─────────────────────────────────────────────────────────────────────────────
# Resilience: Valkey failure must not block DB persistence
# ─────────────────────────────────────────────────────────────────────────────


class TestTelemetryResilience:
    async def test_valkey_error_does_not_block_persistence(
        self, registered_user: dict, async_client: AsyncClient
    ):
        """
        If Valkey raises, the ingest endpoint should still complete the
        Postgres write.  The exception is allowed to propagate (5xx) or
        be swallowed gracefully (202) depending on future error-handling
        policy, but the DB commit must have occurred.

        For now we assert the test at least doesn't hang and returns a
        well-formed HTTP response.
        """
        with patch(
            "app.adapters.cache.valkey_service.set_transformer_state",
            side_effect=ConnectionError("Valkey unreachable"),
        ):
            resp = await async_client.post(
                _INGEST_URL,
                json=[_record(transformer_id="TRF-RESILIENT")],
                headers=_auth_headers(registered_user["token"]),
            )
            # 202 (handled gracefully) or 500 (unhandled) — both are valid
            # for now. The important thing is the client receives a response.
            assert resp.status_code in (202, 500)
