"""Minimal live smoke test for ArkOpenAIClient.

Usage (set env vars first, then):
    uv run python scripts/live_ai_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys


async def main() -> None:
    if not os.environ.get("RUN_LIVE_AI_TESTS"):
        print("Set RUN_LIVE_AI_TESTS=1 to run live smoke tests.", file=sys.stderr)
        sys.exit(0)

    api_key = os.environ.get("ARK_API_KEY", "")
    endpoint = os.environ.get("ARK_EP_DOUBAO_15_LITE", "")
    if not api_key or not endpoint:
        print(
            "ARK_API_KEY and ARK_EP_DOUBAO_15_LITE must be set.", file=sys.stderr
        )
        sys.exit(1)

    # Set env so config picks them up
    os.environ.setdefault("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

    from app.ai.client import ArkOpenAIClient

    client = ArkOpenAIClient()

    print("=== 1. complete() ===")
    text = await client.complete(
        system="你是一个简洁的助手。",
        user="用一句话介绍豆包。",
        endpoint_id=endpoint,
    )
    print(f"  → {text[:120]}")
    assert len(text) > 0, "complete() returned empty string"

    print("=== 2. complete_json() ===")
    from app.ai.json_utils import parse_json_response

    raw = await client.complete_json(
        system="你只能输出 JSON，不能输出其他内容。",
        user='请输出 {"status": "ok"}',
        endpoint_id=endpoint,
    )
    parsed = parse_json_response(raw)
    print(f"  → {parsed}")
    assert isinstance(parsed, dict), "complete_json() did not return a dict"

    print("=== 3. stream() ===")
    gen = await client.stream(
        system="你是一个助手。",
        user="数到三。",
        endpoint_id=endpoint,
    )
    chunks: list[str] = []
    async for chunk in gen:
        chunks.append(chunk)
        print(f"  chunk: {chunk!r}")
        if len(chunks) > 30:
            break
    assert chunks, "stream() yielded no chunks"

    print("\n✓ All smoke tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
