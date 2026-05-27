"""Minimal live smoke test for DeepSeek + 智谱 GLM-4.6V.

Usage:
    uv run python scripts/live_ai_smoke.py
"""

from __future__ import annotations

import asyncio
import sys


def _configure_stdout() -> None:
    """Make Windows consoles tolerate model output with emoji/non-GBK chars."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _check_config() -> None:
    from app.core.config import get_settings

    settings = get_settings()
    provider = settings.ai_provider.strip().lower()
    if provider == "mock":
        print(
            "AI_PROVIDER=mock — set AI_PROVIDER=deepseek in .env to run live smoke tests.",
            file=sys.stderr,
        )
        sys.exit(0)

    if provider == "deepseek" and not settings.deepseek_api_key:
        print("DEEPSEEK_API_KEY not set.", file=sys.stderr)
        sys.exit(1)


async def main() -> None:
    _configure_stdout()
    _check_config()

    from app.core.config import get_settings

    settings = get_settings()

    # ---- 1. DeepSeek complete() ----
    print("=== 1. DeepSeek complete() ===")
    from app.ai.factory import get_ai_client

    client = get_ai_client()
    model = getattr(settings, "deepseek_model_pro", "deepseek-v4-flash")

    text = await client.complete(
        system="你是一个简洁的助手。",
        user="用一句话介绍珀莱雅。",
        endpoint_id=model,
    )
    print(f"  → {text[:200]}")
    assert len(text) > 0, "complete() returned empty string"

    # ---- 2. DeepSeek complete_json() ----
    print("=== 2. DeepSeek complete_json() ===")
    from app.ai.json_utils import parse_json_response

    raw = await client.complete_json(
        system="你只能输出 JSON，不能输出其他内容。",
        user='请输出 {"status": "ok", "brand": "珀莱雅"}',
        endpoint_id=model,
    )
    parsed = parse_json_response(raw)
    print(f"  → {parsed}")
    assert isinstance(parsed, dict), "complete_json() did not return a dict"

    # ---- 3. DeepSeek stream() ----
    print("=== 3. DeepSeek stream() ===")
    flash_model = getattr(settings, "deepseek_model_flash", "deepseek-v4-flash")
    gen = await client.stream(
        system="你是一个助手。",
        user="用三句话介绍珀莱雅红宝石面霜。",
        endpoint_id=flash_model,
    )
    chunks: list[str] = []
    async for chunk in gen:
        chunks.append(chunk)
        print(f"  chunk: {chunk!r}")
        if len(chunks) > 50:
            break
    assert chunks, "stream() yielded no chunks"
    print(f"  full: {''.join(chunks)}")

    # ---- 4. 智谱 GLM-4.6V 文字模式 (optional) ----
    zhipu_key = getattr(settings, "zhipu_api_key", "")
    if zhipu_key:
        print("=== 4. 智谱 GLM-4.6V complete() — 文字模式 ===")
        from app.ai.factory import get_vision_client

        vision_client = get_vision_client()
        vision_model = getattr(settings, "zhipu_model_vision", "glm-4.6v")
        vision_prompt = (
            "请分析一款名为'珀莱雅红宝石面霜'的产品，价格239元，"
            "主打成分是六胜肽和A醇。输出包含 name, price, "
            "key_ingredients, main_selling_points 字段的 JSON。"
        )
        vision_text = await vision_client.complete(
            system="你是一个美妆产品分析助手。请用 JSON 格式输出分析结果。",
            user=vision_prompt,
            endpoint_id=vision_model,
        )
        print(f"  → {vision_text[:300]}")
        assert len(vision_text) > 0, "vision complete() returned empty string"

        # ---- 5. 智谱 GLM-4.6V 视觉模式 — 图片识别 ----
        print("=== 5. 智谱 GLM-4.6V complete() — 视觉模式（图片识别）===")
        lion_url = (
            "https://upload.wikimedia.org/wikipedia/commons/thumb/7/73/"
            "Lion_waiting_in_Namibia.jpg/640px-Lion_waiting_in_Namibia.jpg"
        )
        vision_img_text = await vision_client.complete(
            system="你是一个图片分析助手，请用中文回答。",
            user="请描述图片中的主体是什么动物？有什么特征？",
            endpoint_id=vision_model,
            images=[lion_url],
        )
        print(f"  → {vision_img_text[:300]}")
        assert len(vision_img_text) > 0, "vision image complete() returned empty string"
        assert any(w in vision_img_text for w in ["狮", "lion", "猫科", "幼", "Lion", "哺乳"]), \
            f"视觉识别未返回预期内容: {vision_img_text}"
        print("  [视觉识别] OK — 图片识别管道畅通 ✓")
    else:
        print("=== 4/5. 智谱 GLM-4.6V — SKIPPED (ZHIPU_API_KEY not set) ===")

    print("\n[ok] All smoke tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
