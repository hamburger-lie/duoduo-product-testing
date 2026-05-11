from __future__ import annotations

import pytest

from app.ai.client import AIClient, MockAIClient


@pytest.mark.asyncio
async def test_mock_client_complete_returns_string() -> None:
    client = MockAIClient()
    result = await client.complete(system="sys", user="hello", endpoint_id="ep-test")
    assert isinstance(result, str)
    assert len(result) > 0
    assert "ep-test" in result


@pytest.mark.asyncio
async def test_mock_client_complete_json_is_parseable() -> None:
    import json

    client = MockAIClient()
    raw = await client.complete_json(system="sys", user="hello", endpoint_id="ep-json")
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)
    assert parsed.get("mock") is True


@pytest.mark.asyncio
async def test_mock_client_stream_yields_chunks() -> None:
    client = MockAIClient()
    gen = await client.stream(system="sys", user="hello", endpoint_id="ep-stream")
    chunks: list[str] = []
    async for chunk in gen:
        chunks.append(chunk)
    assert len(chunks) >= 1
    combined = "".join(chunks)
    assert "ep-stream" in combined


def test_mock_client_satisfies_protocol() -> None:
    client = MockAIClient()
    assert isinstance(client, AIClient)
