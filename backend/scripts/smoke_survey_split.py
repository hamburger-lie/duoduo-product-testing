"""One-off smoke test: real DeepSeek call, split-batch survey generation.

Run from soul-unified/:
    .venv/Scripts/python.exe scripts/smoke_survey_split.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(message)s")


class _FakeProduct:
    id = 1
    name = "珀莱雅双抗精华2.0"
    description = "添加虾青素、麦角硫因、肌肽，主打抗氧化抗糖化，改善暗沉初老"
    category = "护肤"
    brand = "珀莱雅"
    price = 169.0
    ai_summary: dict[str, object] | None = {
        "main_selling_points": ["双抗", "抗糖化", "提亮"],
        "key_ingredients": ["虾青素", "麦角硫因", "肌肽"],
        "competitive_position": "同价位精华竞品（如薇诺娜、修丽可平替）",
        "target_channel": "抖音直播、小红书种草",
        "usage_scenarios": ["晚间护肤", "熬夜后急救"],
        "price": 169.0,
    }


async def main() -> None:
    from app.ai.adapters.structured_generation import SurveyGenerationAdapter
    from app.ai.factory import get_ai_client

    ai_client = get_ai_client()
    adapter = SurveyGenerationAdapter(ai_client=ai_client)

    started = time.monotonic()
    questions = await adapter.generate_questions(
        product=_FakeProduct(), extra_focus=None
    )
    elapsed = time.monotonic() - started

    print(f"\n=== elapsed: {elapsed:.1f}s, total questions: {len(questions)} ===\n")

    ids = [q["id"] for q in questions]
    dims = [q["dim"] for q in questions]
    types = [q["type"] for q in questions]

    print("ids:", ids)
    print("dims:", dims)
    print("type counts:", {t: types.count(t) for t in set(types)})

    print("\n--- full questions ---")
    print(json.dumps(questions, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
