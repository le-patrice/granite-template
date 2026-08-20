"""
Idempotency-Key validation and response caching middleware.

Protects state-mutating HTTP methods (POST, PUT, PATCH) against duplicate
execution caused by network retries or client retransmissions.

Lifecycle:
1. Inspects the `Idempotency-Key` HTTP header.
2. If present, checks Valkey for `idempotency:<key>`.
   - If status is 'IN_PROGRESS': returns 409 Conflict (Concurrent request with same key).
   - If status is 'COMPLETED': returns cached status code, headers, and body.
   - If not found: records state as 'IN_PROGRESS' with a 30s lock TTL, processes the
     request, and stores the resulting response with a 24-hour TTL (86400s).
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from litestar.datastructures import MutableScopeHeaders
from litestar.enums import ScopeType
from litestar.middleware.base import AbstractMiddleware
from litestar.status_codes import HTTP_409_CONFLICT
from litestar.types import ASGIApp, Message, Receive, Scope, Send

from app.core.settings import settings

logger = structlog.get_logger()

IDEMPOTENCY_HEADER = "idempotency-key"
IDEMPOTENCY_TTL_SECONDS = 86400  # 24 hours
LOCK_TTL_SECONDS = 60  # in-flight lock


class IdempotencyMiddleware(AbstractMiddleware):
    """ASGI Middleware to enforce Idempotency-Key semantics."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != ScopeType.HTTP or scope["method"] not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return

        headers = MutableScopeHeaders(scope)
        idempotency_key = headers.get(IDEMPOTENCY_HEADER)

        if not idempotency_key:
            await self.app(scope, receive, send)
            return

        cache_key = f"idempotency:{idempotency_key}"
        valkey_client = await self._get_valkey()

        if valkey_client is not None:
            try:
                cached_data = await valkey_client.get(cache_key)
                if cached_data:
                    record = json.loads(cached_data)
                    if record.get("status") == "IN_PROGRESS":
                        # In-flight concurrent request
                        await self._send_json_response(
                            send,
                            status_code=HTTP_409_CONFLICT,
                            payload={
                                "detail": "A request with this Idempotency-Key is currently in progress."
                            },
                        )
                        return

                    if record.get("status") == "COMPLETED":
                        # Return cached response
                        logger.info("idempotency.cache_hit", key=idempotency_key)
                        await self._send_cached_response(send, record)
                        return

                # Acquire in-flight lock
                in_progress_record = json.dumps({"status": "IN_PROGRESS"})
                await valkey_client.set(cache_key, in_progress_record, ex=LOCK_TTL_SECONDS)
            except Exception as exc:  # noqa: BLE001
                logger.warning("idempotency.valkey_error", error=str(exc))

        # Capture response body and status
        response_status = 200
        response_headers: list[tuple[bytes, bytes]] = []
        response_body: list[bytes] = []

        async def capturing_send(message: Message) -> None:
            nonlocal response_status, response_headers
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = list(message.get("headers", []))
                await send(message)
            elif message["type"] == "http.response.body":
                response_body.append(message.get("body", b""))
                await send(message)
            else:
                await send(message)

        try:
            await self.app(scope, receive, capturing_send)
        except Exception:
            # On unhandled error, clear in-flight lock
            if valkey_client is not None:
                try:
                    await valkey_client.delete(cache_key)
                except Exception:  # noqa: S110, BLE001
                    pass
            raise

        # Save successful / completed response in cache
        if valkey_client is not None and 200 <= response_status < 400:
            try:
                full_body = b"".join(response_body).decode("utf-8", errors="replace")
                cached_headers = [
                    (k.decode("latin-1"), v.decode("latin-1"))
                    for k, v in response_headers
                    if k.decode("latin-1").lower() in ("content-type", "x-request-id")
                ]
                record = {
                    "status": "COMPLETED",
                    "status_code": response_status,
                    "headers": cached_headers,
                    "body": full_body,
                }
                await valkey_client.set(cache_key, json.dumps(record), ex=IDEMPOTENCY_TTL_SECONDS)
            except Exception as exc:  # noqa: BLE001
                logger.warning("idempotency.cache_save_error", error=str(exc))

    async def _get_valkey(self) -> Any:
        try:
            import valkey.asyncio as valkey

            return valkey.Valkey(
                host=settings.VALKEY_HOST,
                port=settings.VALKEY_PORT,
                decode_responses=True,
                socket_timeout=2.0,
            )
        except Exception:  # noqa: BLE001
            return None

    async def _send_json_response(self, send: Send, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    async def _send_cached_response(self, send: Send, record: dict) -> None:
        body = record.get("body", "").encode("utf-8")
        headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in record.get("headers", [])]
        headers.append((b"x-cache-idempotent", b"HIT"))
        headers.append((b"content-length", str(len(body)).encode("ascii")))

        await send(
            {
                "type": "http.response.start",
                "status": record.get("status_code", 200),
                "headers": headers,
            }
        )
        await send({"type": "http.response.body", "body": body, "more_body": False})
