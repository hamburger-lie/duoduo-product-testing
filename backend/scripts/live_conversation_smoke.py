"""Minimal live smoke test for conversation AI streaming.

Usage (set env vars first, then):
    uv run python scripts/live_conversation_smoke.py
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

    os.environ.setdefault("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

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
    print(f"\n✓ Conversation smoke test passed. Total chars: {len(combined)}")


if __name__ == "__main__":
    asyncio.run(main())
