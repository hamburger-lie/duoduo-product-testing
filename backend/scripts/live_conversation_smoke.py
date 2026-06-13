"""Minimal live smoke test for conversation AI streaming.

Usage:
    uv run python scripts/live_conversation_smoke.py
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
    from app.ai.prompt_manager import render_prompt

    client = ArkOpenAIClient()

    persona = {
        "name": "林雪",
        "age": 28,
        "city": "上海",
        "occupation": "产品经理",
        "persona_tag": "成分党",
        "profile": {"skin_type": "混合偏干"},
    }
    product_summary = {
        "name": "测试面霜",
        "description": "温和保湿面霜",
        "category": "护肤",
        "brand": "TestBrand",
    }
    answer_history = [
        {
            "overall_intent": 4,
            "sentiment": "positive",
            "answers": [
                {"qid": "q01", "answer": 4, "reason": "质地不错"},
            ],
        }
    ]
    conversation_history = [
        {"role": "user", "content": "你好，想了解一下你对这款面霜的看法"},
    ]

    prompt, _, _ = render_prompt(
        "persona_chat",
        persona=persona,
        product_ai_summary=product_summary,
        persona_answer_history=answer_history,
        conversation_history=conversation_history,
        user_message="你觉得这个面霜的性价比怎么样？",
    )

    print("=== Streaming persona chat ===")
    system = "你是一个消费者角色扮演助手。严格按照角色人设回答，不要暴露 AI 身份。"

    gen = await client.stream(
        system=system,
        user=prompt,
        endpoint_id=endpoint,
    )

    chunks: list[str] = []
    async for chunk in gen:
        chunks.append(chunk)
        print(chunk, end="", flush=True)
        if len(chunks) > 100:
            break

    print()
    combined = "".join(chunks)
    assert len(combined) > 0, "stream() yielded no content"
    print(f"\n[ok] Conversation smoke test passed. Total chars: {len(combined)}")


if __name__ == "__main__":
    asyncio.run(main())
