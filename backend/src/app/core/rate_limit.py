"""Atomic Sliding Window Rate Limiter powered by Valkey."""

from __future__ import annotations

import json
import time

import structlog
from litestar.middleware.base import AbstractMiddleware
from litestar.types import ASGIApp, Receive, Scope, Send

from app.core.cache import get_valkey_pool

logger = structlog.get_logger("app.ratelimit")

LUA_SLIDING_WINDOW = """
local current_key = KEYS[1]
local prev_key = KEYS[2]
local limit = tonumber(ARGV[1])
local current_weight = tonumber(ARGV[2])

local current_count = tonumber(redis.call('get', current_key) or '0')
local prev_count = tonumber(redis.call('get', prev_key) or '0')

local estimated_count = math.floor(prev_count * (1 - current_weight) + current_count)

if estimated_count >= limit then
    return {0, limit - estimated_count, estimated_count}
else
    redis.call('incr', current_key)
    redis.call('expire', current_key, 120)
    return {1, limit - (estimated_count + 1), estimated_count + 1}
end
"""


class SlidingWindowRateLimitMiddleware(AbstractMiddleware):
    """Sliding-window atomic rate limiter evaluating traffic quotas per category and IP."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self.valkey = get_valkey_pool()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Determine quota policy
        if "/api/v1/auth/login" in path:
            limit = 5
            category = "auth"
        elif "/api/v1/whatsapp" in path:
            limit = 500
            category = "webhook"
        else:
            limit = 120
            category = "api"

        client_ip = "127.0.0.1"
        for header, value in scope.get("headers", []):
            if header == b"x-forwarded-for":
                client_ip = value.decode("utf-8", errors="ignore").split(",")[0].strip()
                break
        else:
            client = scope.get("client")
            if client and len(client) > 0 and client[0]:
                client_ip = str(client[0])

        now = int(time.time())
        window_size = 60
        current_window = now // window_size
        prev_window = current_window - 1
        current_weight = (now % window_size) / window_size

        key_current = f"rl:{category}:{client_ip}:{current_window}"
        key_prev = f"rl:{category}:{client_ip}:{prev_window}"

        try:
            valkey_client = get_valkey_pool()
            result = await valkey_client.eval(
                LUA_SLIDING_WINDOW, 2, key_current, key_prev, limit, current_weight
            )
            allowed, remaining, _total = result[0], result[1], result[2]
        except Exception as exc:  # noqa: BLE001
            logger.warning("ratelimit.valkey_error", error=str(exc))
            # Fail open to guarantee resilience if cache cluster drops
            await self.app(scope, receive, send)
            return

        reset_time = window_size - (now % window_size)

        if not allowed:
            body = json.dumps({"error": "Too Many Requests", "retry_after": reset_time}).encode(
                "utf-8"
            )
            headers = [
                (b"content-type", b"application/json"),
                (b"ratelimit-limit", str(limit).encode()),
                (b"ratelimit-remaining", b"0"),
                (b"ratelimit-reset", str(reset_time).encode()),
                (b"retry-after", str(reset_time).encode()),
            ]
            await send({"type": "http.response.start", "status": 429, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return

        # Add rate limit headers to downstream responses when successful
        async def send_with_ratelimit_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"ratelimit-limit", str(limit).encode()))
                headers.append((b"ratelimit-remaining", str(max(0, remaining)).encode()))
                headers.append((b"ratelimit-reset", str(reset_time).encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_ratelimit_headers)
