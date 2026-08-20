"""
Asynchronous Circuit Breaker state machine for distributed systems resilience.

States:
  • CLOSED: Normal operation. Requests pass through. Failures are counted.
  • OPEN: Threshold exceeded. Requests immediately fail with CircuitOpenException.
  • HALF_OPEN: Cooldown elapsed. A limited number of trial requests are permitted.
"""

from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitOpenException(Exception):
    """Raised when an operation is attempted on an OPEN circuit breaker."""

    def __init__(self, name: str, retry_after: float):
        super().__init__(f"Circuit breaker '{name}' is OPEN. Retry after {retry_after:.1f}s")
        self.name = name
        self.retry_after = retry_after


class CircuitBreaker:
    """
    Thread-safe & asyncio-safe Circuit Breaker.

    Parameters:
        name: Identifier for logs/metrics.
        failure_threshold: Consecutive failures before tripping to OPEN.
        recovery_timeout: Seconds to remain OPEN before transitioning to HALF_OPEN.
        half_open_max_trials: Successful trial calls in HALF_OPEN to reset to CLOSED.
        expected_exceptions: Exception tuple that counts toward failure threshold.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_trials: int = 2,
        expected_exceptions: tuple[type[Exception], ...] = (Exception,),
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_trials = half_open_max_trials
        self.expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_state_change = time.monotonic()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def _check_state_transition(self) -> None:
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_state_change
            if elapsed >= self.recovery_timeout:
                logger.info(
                    "circuit_breaker.transition",
                    name=self.name,
                    from_state=self._state.value,
                    to_state=CircuitState.HALF_OPEN.value,
                )
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                self._last_state_change = time.monotonic()

    async def call(self, fn: Callable[..., Coroutine[Any, Any, T]], *args: Any, **kwargs: Any) -> T:
        async with self._lock:
            await self._check_state_transition()

            if self._state == CircuitState.OPEN:
                retry_after = self.recovery_timeout - (time.monotonic() - self._last_state_change)
                raise CircuitOpenException(self.name, max(0.0, retry_after))

        try:
            result = await fn(*args, **kwargs)
        except self.expected_exceptions as exc:
            async with self._lock:
                await self._on_failure(exc)
            raise

        async with self._lock:
            await self._on_success()

        return result

    async def _on_success(self) -> None:
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_max_trials:
                logger.info(
                    "circuit_breaker.transition",
                    name=self.name,
                    from_state=self._state.value,
                    to_state=CircuitState.CLOSED.value,
                )
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._last_state_change = time.monotonic()
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    async def _on_failure(self, exc: Exception) -> None:
        self._failure_count += 1
        logger.warning(
            "circuit_breaker.failure",
            name=self.name,
            state=self._state.value,
            failure_count=self._failure_count,
            error=str(exc),
        )

        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
            logger.error(
                "circuit_breaker.transition",
                name=self.name,
                from_state=self._state.value,
                to_state=CircuitState.OPEN.value,
                threshold=self.failure_threshold,
            )
            self._state = CircuitState.OPEN
            self._last_state_change = time.monotonic()

    def __call__(
        self, fn: Callable[..., Coroutine[Any, Any, T]]
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await self.call(fn, *args, **kwargs)

        return wrapper
