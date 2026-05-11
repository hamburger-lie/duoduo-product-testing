"""Live integration tests for ArkOpenAIClient.

These tests make real network calls to 火山方舟 and are skipped by default.
Run with RUN_LIVE_AI_TESTS=1 ARK_API_KEY=<key> ARK_EP_DOUBAO_15_LITE=<ep>
then: uv run pytest tests/ai/test_ark_live.py -v
"""

from __future__ import annotations

import os

import pytest

_LIVE = bool(os.environ.get("RUN_LIVE_AI_TESTS"))
_KEY = os.environ.get("ARK_API_KEY", "")
_skip = pytest.mark.skipif(
    not (_LIVE and _KEY),
    reason="Set RUN_LIVE_AI_TESTS=1 and ARK_API_KEY to run live tests",
)


@_skip
@pytest.mark.asyncio
async def test_ark_complete_returns_non_empty_string() -> None:
    from app.ai.client import ArkOpenAIClient

    client = ArkOpenAIClient()
    ep = os.environ.get("ARK_EP_DOUBAO_15_LITE", "")
    result = await client.complete(
        system="你是一个简洁的助手。",
        user="用一句话介绍你自己。",
        endpoint_id=ep,
    )
    assert isinstance(result, str)
    assert len(result) > 0


@_skip
@pytest.mark.asyncio
async def test_ark_complete_json_returns_valid_json() -> None:
    from app.ai.client import ArkOpenAIClient
    from app.ai.json_utils import parse_json_response

    client = ArkOpenAIClient()
    ep = os.environ.get("ARK_EP_DOUBAO_15_LITE", "")
    result = await client.complete_json(
        system="你只能输出 JSON，不能输出其他内容。",
        user='请输出一个 JSON 对象，包含字段 "status" 值为 "ok"。',
        endpoint_id=ep,
    )
    parsed = parse_json_response(result)
    assert isinstance(parsed, dict)


@_skip
@pytest.mark.asyncio
async def test_ark_stream_yields_delta_chunks() -> None:
    from app.ai.client import ArkOpenAIClient

    client = ArkOpenAIClient()
    ep = os.environ.get("ARK_EP_DOUBAO_15_LITE", "")
    gen = await client.stream(
        system="你是一个助手。",
        user="数到三，每个数字单独输出。",
        endpoint_id=ep,
    )
    chunks: list[str] = []
    async for chunk in gen:
        chunks.append(chunk)
        if len(chunks) > 20:
            break
    assert len(chunks) >= 1
    combined = "".join(chunks)
    assert len(combined) > 0
