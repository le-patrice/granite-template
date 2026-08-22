"""Valkey connection pool and client factory."""

from __future__ import annotations

from typing import Any

import structlog

from app.core.settings import settings

logger = structlog.get_logger("app.cache")
_valkey_pool: Any = None


def get_valkey_pool() -> Any:
    """Return a shared asynchronous Valkey/Redis connection client."""
    global _valkey_pool
    if _valkey_pool is None:
        try:
            import valkey.asyncio as valkey

            _valkey_pool = valkey.Valkey(
                host=settings.VALKEY_HOST,
                port=settings.VALKEY_PORT,
                decode_responses=False,
                socket_connect_timeout=2,
            )
        except ImportError:
            import redis.asyncio as redis

            _valkey_pool = redis.Redis(
                host=settings.VALKEY_HOST,
                port=settings.VALKEY_PORT,
                decode_responses=False,
                socket_connect_timeout=2,
            )
    return _valkey_pool
