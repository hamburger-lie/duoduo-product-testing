from __future__ import annotations

import re

from httpx import ASGITransport, AsyncClient
from prometheus_client import generate_latest

from app.ai.client import ArkOpenAIClient
from app.main import app


def _counter_value(metrics_text: str, *, path_template: str) -> float:
    pattern = re.compile(
        r'http_requests_total\{[^}]*path_template="'
        + re.escape(path_template)
        + r'"[^}]*\}\s+([0-9.]+)'
    )
    return sum(float(match.group(1)) for match in pattern.finditer(metrics_text))


def _ai_counter_value(metrics_text: str, *, endpoint_id: str, status: str) -> float:
    pattern = re.compile(
        r'ai_requests_total\{[^}]*endpoint_id="'
        + re.escape(endpoint_id)
        + r'"[^}]*status="'
        + re.escape(status)
        + r'"[^}]*\}\s+([0-9.]+)'
    )
    return sum(float(match.group(1)) for match in pattern.finditer(metrics_text))


async def test_metrics_endpoint_returns_200() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]


async def test_metrics_contains_http_counter() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/metrics")

    assert "http_requests_total" in response.text


async def test_http_request_increments_counter() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        before = await client.get("/metrics")
        before_count = _counter_value(before.text, path_template="/api/v1/auth/me")

        await client.get("/api/v1/auth/me")

        after = await client.get("/metrics")
        after_count = _counter_value(after.text, path_template="/api/v1/auth/me")

    assert after_count == before_count + 1


async def test_health_excluded_from_metrics() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        before = await client.get("/metrics")
        before_count = _counter_value(before.text, path_template="/health/live")

        await client.get("/health/live")

        after = await client.get("/metrics")
        after_count = _counter_value(after.text, path_template="/health/live")

    assert after_count == before_count


async def test_ai_request_increments_counter() -> None:
    endpoint_id = "metrics-test-endpoint"
    client = ArkOpenAIClient(api_key="fake", base_url="https://fake.example")

    async def fake_complete(
        *,
        system: str,
        user: str,
        endpoint_id: str,
        images: list[str] | None = None,
    ) -> str:
        _ = system, user, endpoint_id, images
        return "ok"

    client._complete = fake_complete  # type: ignore[method-assign]
    before = _ai_counter_value(
        generate_latest().decode("utf-8"),
        endpoint_id=endpoint_id,
        status="success",
    )

    await client.complete(system="sys", user="hi", endpoint_id=endpoint_id)

    after = _ai_counter_value(
        generate_latest().decode("utf-8"),
        endpoint_id=endpoint_id,
        status="success",
    )
    assert after == before + 1
