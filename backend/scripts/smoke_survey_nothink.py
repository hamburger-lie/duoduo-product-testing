"""A/B smoke: split-batch survey generation with thinking disabled / low effort.

Run from soul-unified/:
    .venv/Scripts/python.exe scripts/smoke_survey_nothink.py disabled
    .venv/Scripts/python.exe scripts/smoke_survey_nothink.py low
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx

PRODUCT_SUMMARY = {
    "id": 1,
    "name": "珀莱雅双抗精华2.0",
    "description": "添加虾青素、麦角硫因、肌肽，主打抗氧化抗糖化，改善暗沉初老",
    "category": "护肤",
    "brand": "珀莱雅",
    "price": 169.0,
    "main_selling_points": ["双抗", "抗糖化", "提亮"],
    "key_ingredients": ["虾青素", "麦角硫因", "肌肽"],
    "competitive_position": "同价位精华竞品（如薇诺娜、修丽可平替）",
    "target_channel": "抖音直播、小红书种草",
    "usage_scenarios": ["晚间护肤", "熬夜后急救"],
}


async def call_batch(api_key: str, prompt: str, mode: str) -> tuple[float, int, list]:
    payload: dict = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": "你是专业的市场调研问卷设计专家。严格按 JSON schema 输出。"},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 8000,
    }
    if mode == "disabled":
        payload["thinking"] = {"type": "disabled"}
    else:
        payload["reasoning_effort"] = mode

    started = time.monotonic()
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            "https://api.deepseek.com/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    elapsed = time.monotonic() - started
    body = resp.json()
    if "error" in body:
        raise RuntimeError(body["error"]["message"][:200])
    details = body["usage"].get("completion_tokens_details") or {}
    reasoning = details.get("reasoning_tokens") or 0
    content = body["choices"][0]["message"]["content"]
    from app.ai.json_utils import parse_json_response

    try:
        questions = parse_json_response(content)["questions"]
    except Exception as exc:
        print(f"  [batch json invalid after {elapsed:.1f}s: {type(exc).__name__}]")
        questions = []
    return elapsed, reasoning, questions


async def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "disabled"

    from app.ai.prompt_manager import render_prompt
    from app.core.config import get_settings

    api_key = get_settings().deepseek_api_key
    prompts = [
        render_prompt(
            "survey_generate",
            user_role_type="manufacturer",
            product_ai_summary=PRODUCT_SUMMARY,
            extra_focus="",
            product={"id": 1},
            batch=b,
        )[0]
        for b in (1, 2)
    ]

    started = time.monotonic()
    results = await asyncio.gather(
        call_batch(api_key, prompts[0], mode),
        call_batch(api_key, prompts[1], mode),
    )
    total = time.monotonic() - started

    print(f"\n=== mode={mode} TOTAL wall: {total:.1f}s ===")
    for i, (elapsed, reasoning, questions) in enumerate(results, start=1):
        print(f"batch{i}: {elapsed:.1f}s reasoning_tokens={reasoning} questions={len(questions)}")

    merged = results[0][2] + results[1][2]
    print(f"merged: {len(merged)} questions")
    sample = [merged[i] for i in (0, 7, 13, 18, 26, 28) if i < len(merged)]
    print(json.dumps(sample, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
