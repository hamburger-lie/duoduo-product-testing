"""Generate one full 30-question survey via the real adapter, dump to JSON.

Usage:
    python scripts/gen_survey_sample.py <out.json>

Honors SURVEY_DISABLE_THINKING from settings (set in .env).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time


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
    out = sys.argv[1]
    from app.ai.adapters.structured_generation import SurveyGenerationAdapter
    from app.ai.factory import get_ai_client

    adapter = SurveyGenerationAdapter(ai_client=get_ai_client())
    started = time.monotonic()
    questions = await adapter.generate_questions(product=_FakeProduct(), extra_focus=None)
    elapsed = time.monotonic() - started
    json.dump({"questions": questions}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"wrote {out}: {len(questions)}q in {elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
