from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from enum import Enum
from typing import TypeVar

from app.ai.exceptions import AIServiceUnavailable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitBreakerState(Enum):
    """Circuit breaker state."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Lightweight async circuit breaker for AI provider calls."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        success_threshold: int = 2,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._success_threshold = success_threshold
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        """Return current circuit breaker state."""

        return self._state

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Run an async operation under circuit breaker protection."""

        async with self.protect():
            return await operation()

    @asynccontextmanager
    async def protect(self) -> AsyncIterator[None]:
        """Protect an async operation whose errors may occur during iteration."""

        await self._before_call()
        try:
            yield
        except Exception:
            await self._record_failure()
            raise
        else:
            await self._record_success()

    async def _before_call(self) -> None:
        async with self._lock:
            if self._state is CircuitBreakerState.OPEN:
                if self._can_probe():
                    self._transition_to(CircuitBreakerState.HALF_OPEN)
                    self._success_count = 0
                else:
                    raise AIServiceUnavailable("Circuit breaker is open")

            if self._state is CircuitBreakerState.HALF_OPEN:
                if self._half_open_probe_in_flight:
                    raise AIServiceUnavailable("Circuit breaker is open")
                self._half_open_probe_in_flight = True

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state is CircuitBreakerState.HALF_OPEN:
                self._half_open_probe_in_flight = False
                self._success_count += 1
                if self._success_count >= self._success_threshold:
                    self._reset_counts()
                    self._transition_to(CircuitBreakerState.CLOSED)
                return

            self._failure_count = 0

    async def _record_failure(self) -> None:
        async with self._lock:
            if self._state is CircuitBreakerState.HALF_OPEN:
                self._half_open_probe_in_flight = False
                self._open()
                return

            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._open()

    def _can_probe(self) -> bool:
        return (
            self._opened_at is not None
            and time.monotonic() - self._opened_at >= self._recovery_timeout
        )

    def _open(self) -> None:
        self._success_count = 0
        self._opened_at = time.monotonic()
        self._transition_to(CircuitBreakerState.OPEN)

    def _reset_counts(self) -> None:
        self._failure_count = 0
        self._success_count = 0
        self._opened_at = None

    def _transition_to(self, new_state: CircuitBreakerState) -> None:
        old_state = self._state
        if old_state is new_state:
            return
        self._state = new_state
        logger.warning(
            "circuit_breaker_state_change from=%s to=%s",
            old_state.value,
            new_state.value,
        )
