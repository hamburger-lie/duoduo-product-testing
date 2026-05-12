"""Minimal live smoke test for ArkOpenAIClient.

Usage:
    uv run python scripts/live_ai_smoke.py
"""

from __future__ import annotations

import asyncio
import os
import sys


def _configure_stdout() -> None:
    """Make Windows consoles tolerate model output with emoji/non-GBK chars."""

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _load_live_config() -> tuple[str, str]:
    """Load live config from environment or local .env via Settings."""

    from app.core.config import get_settings

    settings = get_settings()
    if os.environ.get("RUN_LIVE_AI_TESTS") != "1" and settings.ai_provider != "ark":
        print(
            "Set RUN_LIVE_AI_TESTS=1 or AI_PROVIDER=ark to run live smoke tests.",
            file=sys.stderr,
        )
        sys.exit(0)

    api_key = os.environ.get("ARK_API_KEY") or settings.ark_api_key
    endpoint = os.environ.get("ARK_EP_DOUBAO_15_LITE") or settings.ark_ep_doubao_15_lite
    os.environ.setdefault("ARK_API_KEY", api_key)
    os.environ.setdefault("ARK_EP_DOUBAO_15_LITE", endpoint)
    os.environ.setdefault("ARK_BASE_URL", settings.ark_base_url)

    if not api_key or not endpoint:
        print(
            "ARK_API_KEY and ARK_EP_DOUBAO_15_LITE must be set in environment or .env.",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key, endpoint


async def main() -> None:
    _configure_stdout()
    _, endpoint = _load_live_config()

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

    print("\n[ok] All smoke tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
