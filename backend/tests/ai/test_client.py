from __future__ import annotations

from decimal import Decimal

import pytest

from app.ai.client import AIClient, MockAIClient
from app.ai.usage import AIUsage, estimate_cost_yuan


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


def test_estimate_cost_yuan_from_configured_prices() -> None:
    usage = AIUsage(input_tokens=1000, output_tokens=500)

    result = estimate_cost_yuan(
        usage,
        input_price_per_1k=Decimal("0.0020"),
        output_price_per_1k=Decimal("0.0060"),
    )

    assert result == Decimal("0.0050")


@pytest.mark.asyncio
async def test_mock_client_complete_json_with_usage_returns_zero_usage() -> None:
    client = MockAIClient()

    result = await client.complete_json_with_usage(
        system="sys",
        user="hello",
        endpoint_id="ep-json",
    )

    assert result.content
    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0
    assert result.usage.cost_yuan == Decimal("0.0000")


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


@pytest.mark.asyncio
async def test_mock_client_complete_with_images_notes_image_count() -> None:
    client = MockAIClient()
    result = await client.complete(
        system="sys",
        user="analyze this",
        endpoint_id="ep-vision",
        images=["base64data1", "base64data2"],
    )
    assert "2 image" in result


def test_ark_client_build_messages_text_only() -> None:
    from app.ai.client import ArkOpenAIClient

    client = ArkOpenAIClient(api_key="fake", base_url="https://fake.api")
    msgs = client._build_messages("system text", "user text")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "user text"


def test_ark_client_build_messages_multimodal_raw_base64() -> None:
    from app.ai.client import ArkOpenAIClient

    client = ArkOpenAIClient(api_key="fake", base_url="https://fake.api")
    msgs = client._build_messages("sys", "describe this", images=["abc123"])
    user_msg = msgs[1]
    assert isinstance(user_msg["content"], list)
    content = user_msg["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert content[1]["type"] == "text"
    assert content[1]["text"] == "describe this"


def test_ark_client_build_messages_multimodal_data_url() -> None:
    from app.ai.client import ArkOpenAIClient

    client = ArkOpenAIClient(api_key="fake", base_url="https://fake.api")
    data_url = "data:image/png;base64,iVBORw0KGgo="
    msgs = client._build_messages("sys", "describe", images=[data_url])
    content = msgs[1]["content"]
    assert isinstance(content, list)
    assert content[0]["image_url"]["url"] == data_url


def test_ark_client_build_messages_multimodal_https_url() -> None:
    from app.ai.client import ArkOpenAIClient

    client = ArkOpenAIClient(api_key="fake", base_url="https://fake.api")
    https_url = "https://cdn.example.com/product.jpg"
    msgs = client._build_messages("sys", "describe", images=[https_url])
    content = msgs[1]["content"]
    assert isinstance(content, list)
    assert content[0]["image_url"]["url"] == https_url
