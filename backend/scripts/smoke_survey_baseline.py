"""Baseline smoke test: single 30-question call (pre-split prompt path).

Run from soul-unified/:
    .venv/Scripts/python.exe scripts/smoke_survey_baseline.py
"""
from __future__ import annotations

import asyncio
import time

from app.ai.json_utils import parse_json_response, validate_required_keys
from app.ai.models import ModelRouter, TaskType
from app.ai.prompt_manager import render_prompt


async def main() -> None:
    from app.ai.factory import get_ai_client

    ai_client = get_ai_client()
    route = ModelRouter().get(TaskType.SURVEY_GENERATE)

    product_summary = {
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

    prompt, _, _ = render_prompt(
        "survey_generate",
        user_role_type="manufacturer",
        product_ai_summary=product_summary,
        extra_focus="",
        product={"id": 1},
        # batch omitted -> defaults to 0 -> original 30-question prompt
    )

    started = time.monotonic()
    raw_json = await ai_client.complete_json(
        system="你是专业的市场调研问卷设计专家。严格按 JSON schema 输出。",
        user=prompt,
        endpoint_id=route.endpoint_id,
    )
    elapsed = time.monotonic() - started

    data = parse_json_response(raw_json)
    validate_required_keys(data, ["questions"])
    questions = data["questions"]

    print(f"\n=== BASELINE (single 30Q call) elapsed: {elapsed:.1f}s, total: {len(questions)} ===\n")


if __name__ == "__main__":
    asyncio.run(main())
