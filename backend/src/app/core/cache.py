"""Valkey connection pool and client factory."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.core.settings import settings

logger = structlog.get_logger("app.cache")
_valkey_pools: dict[asyncio.AbstractEventLoop, Any] = {}
_fallback_valkey_pool: Any = None


def _create_valkey_client() -> Any:
    """Instantiate a low-level async Valkey or Redis client."""
    try:
        import valkey.asyncio as valkey

        return valkey.Valkey(
            host=settings.VALKEY_HOST,
            port=settings.VALKEY_PORT,
            decode_responses=False,
            socket_connect_timeout=2,
        )
    except ImportError:
        import redis.asyncio as redis

        return redis.Redis(
            host=settings.VALKEY_HOST,
            port=settings.VALKEY_PORT,
            decode_responses=False,
            socket_connect_timeout=2,
        )


def get_valkey_pool() -> Any:
    """Return a shared asynchronous Valkey/Redis connection client tied to current event loop."""
    global _fallback_valkey_pool

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        closed = [lp for lp in _valkey_pools if lp.is_closed()]
        for lp in closed:
            _valkey_pools.pop(lp, None)

        if loop in _valkey_pools:
            return _valkey_pools[loop]

    client = _create_valkey_client()
    if loop is not None:
        _valkey_pools[loop] = client
    else:
        _fallback_valkey_pool = client
    return client
