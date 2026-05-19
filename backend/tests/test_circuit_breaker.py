from __future__ import annotations

import asyncio

import pytest

from app.ai.circuit_breaker import CircuitBreaker, CircuitBreakerState
from app.ai.client import MockAIClient
from app.ai.exceptions import AIServiceUnavailable


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_consecutive_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2, recovery_timeout=30.0)

    async def fail() -> str:
        raise AIServiceUnavailable("provider down")

    with pytest.raises(AIServiceUnavailable):
        await breaker.call(fail)
    assert breaker.state is CircuitBreakerState.CLOSED

    with pytest.raises(AIServiceUnavailable):
        await breaker.call(fail)

    assert breaker.state is CircuitBreakerState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_rejects_immediately_when_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=30.0)
    calls = 0

    async def fail() -> str:
        nonlocal calls
        calls += 1
        raise AIServiceUnavailable("provider down")

    with pytest.raises(AIServiceUnavailable):
        await breaker.call(fail)

    with pytest.raises(AIServiceUnavailable, match="Circuit breaker is open"):
        await breaker.call(fail)

    assert calls == 1


@pytest.mark.asyncio
async def test_circuit_breaker_moves_to_half_open_after_recovery_timeout() -> None:
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=0.01,
        success_threshold=2,
    )

    async def fail() -> str:
        raise AIServiceUnavailable("provider down")

    async def succeed() -> str:
        return "ok"

    with pytest.raises(AIServiceUnavailable):
        await breaker.call(fail)
    await asyncio.sleep(0.02)

    result = await breaker.call(succeed)

    assert result == "ok"
    assert breaker.state is CircuitBreakerState.HALF_OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_recovers_from_half_open_to_closed() -> None:
    breaker = CircuitBreaker(
        failure_threshold=1,
        recovery_timeout=0.01,
        success_threshold=2,
    )

    async def fail() -> str:
        raise AIServiceUnavailable("provider down")

    async def succeed() -> str:
        return "ok"

    with pytest.raises(AIServiceUnavailable):
        await breaker.call(fail)
    await asyncio.sleep(0.02)

    await breaker.call(succeed)
    await breaker.call(succeed)

    assert breaker.state is CircuitBreakerState.CLOSED


@pytest.mark.asyncio
async def test_circuit_breaker_returns_to_open_when_half_open_probe_fails() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout=0.01)

    async def fail() -> str:
        raise AIServiceUnavailable("provider down")

    with pytest.raises(AIServiceUnavailable):
        await breaker.call(fail)
    await asyncio.sleep(0.02)

    with pytest.raises(AIServiceUnavailable):
        await breaker.call(fail)

    assert breaker.state is CircuitBreakerState.OPEN


@pytest.mark.asyncio
async def test_mock_ai_client_does_not_use_circuit_breaker() -> None:
    client = MockAIClient()

    assert not hasattr(client, "_circuit_breaker")
    assert await client.complete(system="sys", user="hi", endpoint_id="mock")
