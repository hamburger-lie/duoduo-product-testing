"""Persona scoring stress test - direct prompt rendering + AI call.

Tests scoring distribution, persona differentiation, and context card effects.

Usage:
    cd backend
    uv run python scripts/persona_scoring_test.py
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
from pathlib import Path

# Fix Windows GBK encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add backend to path
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("AI_PROVIDER", "deepseek")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///tmp_test.db")

from app.ai.prompt_manager import render_prompt
from app.ai.json_utils import parse_json_response
from app.ai.factory import get_ai_client
from app.ai.models import ModelRouter, TaskType

# -- Personas --
PERSONAS_DIR = BACKEND_ROOT.parent / "docs" / "SEEDS" / "personas_v2"

def load_personas():
    personas = []
    for f in sorted(PERSONAS_DIR.glob("persona_beauty_*.json")):
        with open(f, "r", encoding="utf-8") as fh:
            personas.append(json.load(fh))
    return personas

# -- Products --
PRODUCTS = [
    {
        "name": "polaiya_shuangkang",
        "display": "珀莱雅双抗精华2.0",
        "brand": "珀莱雅",
        "price": 99,
        "description": "含虾青素、麦角硫因，主打抗氧抗糖双抗功效，轻薄水润质地，适合日常护肤第一步。天猫销量榜前五，小红书10万+笔记。",
        "selling_point": "双抗精华，抗氧化+抗糖化",
        "target_audience": "20-35岁，关注初老和暗沉的女性",
    },
    {
        "name": "dabao_sod",
        "display": "大宝SOD蜜",
        "brand": "大宝",
        "price": 29,
        "description": "经典国货保湿乳液，含SOD成分，质地清爽，基础保湿。超市随处可买，无需做功课。",
        "selling_point": "国货经典，基础保湿，便宜大碗",
        "target_audience": "不挑剔的大众消费者",
    },
    {
        "name": "skinceuticals_ce",
        "display": "修丽可CE精华",
        "brand": "修丽可(SkinCeuticals)",
        "price": 680,
        "description": "15%左旋VC+1%VE+0.5%阿魏酸，Duke大学专利配方，有多项临床试验数据支持抗氧化和光老化修护。质地偏油，需要建立耐受。",
        "selling_point": "专利黄金比例抗氧化，临床数据背书",
        "target_audience": "成分党、高预算护肤爱好者",
    },
    {
        "name": "winona_cream",
        "display": "薇诺娜舒敏保湿特护霜",
        "brand": "薇诺娜",
        "price": 198,
        "description": "含青刺果油、马齿苋提取物，皮肤科医生推荐的敏感肌专用面霜。质地厚润，适合干皮和敏感期使用。",
        "selling_point": "皮肤科背书，敏感肌修护",
        "target_audience": "敏感肌、干皮消费者",
    },
    {
        "name": "hbn_retinol",
        "display": "HBN视黄醇晚霜",
        "brand": "HBN",
        "price": 149,
        "description": "0.1%视黄醇+神经酰胺，主打夜间抗皱修护。新锐国货，小红书口碑好但部分用户反映有轻微刺激。京东销量榜前十。",
        "selling_point": "视黄醇抗皱，国货平替",
        "target_audience": "25-35岁，关注抗初老的性价比消费者",
    },
]

# -- Context Cards --
CONTEXT_CARDS = {
    "default": "",
    "payday": "今天刚发了工资，卡里余额看着很舒服。晚上吃完饭躺在沙发上刷手机，心情不错，看到什么好东西都觉得可以犒劳一下自己。",
    "month_end": "这个月花超了，信用卡账单还没还完。本来说这个月不买护肤品了，但刚好刷到直播间在推这个产品，主播说库存只剩最后一批了。",
    "friend_rec": "闺蜜/室友刚买了这个产品，在微信群里发了使用照片说特别好用，还说'你肯定会喜欢'，@了你好几次让你也买。",
}

# -- Simplified Survey --
SURVEY_QUESTIONS = [
    {
        "qid": "q1_first_impression",
        "dimension": "第一印象",
        "question_text": "看到这个产品的第一印象是什么？",
        "type": "open",
    },
    {
        "qid": "q2_interest",
        "dimension": "兴趣度",
        "question_text": "你对这个产品的兴趣程度如何？",
        "type": "scale_1_5",
        "scale_labels": {"1": "完全不感兴趣", "5": "非常感兴趣"},
    },
    {
        "qid": "q3_price_feel",
        "dimension": "价格感知",
        "question_text": "你觉得这个产品的价格怎么样？",
        "type": "single",
        "options": ["太便宜了不放心", "很划算", "价格合理", "有点贵但能接受", "太贵了不会买"],
    },
    {
        "qid": "q4_purchase_intent",
        "dimension": "购买意愿",
        "question_text": "你会购买这个产品吗？",
        "type": "single",
        "options": ["一定会买", "很可能会买", "要看情况", "可能不会买", "一定不会买"],
    },
    {
        "qid": "q5_concern",
        "dimension": "顾虑",
        "question_text": "你对这个产品最大的顾虑是什么？",
        "type": "open",
    },
]


async def run_single_test(client, endpoint_id, persona, product, context_card=""):
    """Run one persona answer test, return parsed JSON or None."""
    try:
        rendered, _, _ = render_prompt(
            "persona_answer",
            persona=persona,
            product_ai_summary=product,
            survey_questions=SURVEY_QUESTIONS,
            context_card=context_card if context_card else None,
        )

        raw = await client.complete_json(
            system="你是一个消费者模拟系统。严格按照角色设定回答问卷，只输出JSON。",
            user=rendered,
            endpoint_id=endpoint_id,
        )
        result = parse_json_response(raw)
        return result
    except Exception as e:
        print(f"    [ERROR] {persona['name']} x {product['display']}: {e}")
        return None


async def main():
    personas = load_personas()
    client = get_ai_client()
    router = ModelRouter()
    route = router.get(TaskType.PERSONA_ANSWER)
    endpoint_id = route.endpoint_id

    print(f"AI Provider: {os.environ.get('AI_PROVIDER')}")
    print(f"Endpoint: {endpoint_id}")
    print(f"Personas: {[p['name'] for p in personas]}")
    print(f"Products: {[p['display'] for p in PRODUCTS]}")
    print()

    # -- Phase 1: Score Matrix (5 personas x 5 products) --
    print("=" * 60)
    print("PHASE 1: Score Matrix (5 personas x 5 products = 25 calls)")
    print("=" * 60)

    scores = {}
    sentiments = {}
    verdicts = {}

    for persona in personas:
        pname = persona["name"]
        scores[pname] = {}
        sentiments[pname] = {}
        verdicts[pname] = {}

        for product in PRODUCTS:
            prodname = product["display"]
            print(f"  {pname} x {prodname} (RMB{product['price']})...", end=" ", flush=True)
            result = await run_single_test(client, endpoint_id, persona, product)
            if result:
                score = result.get("overall_intent", "?")
                sent = result.get("sentiment", "?")
                verdict = result.get("one_sentence_verdict", "")
                scores[pname][prodname] = score
                sentiments[pname][prodname] = sent
                verdicts[pname][prodname] = verdict
                print(f"-> {score} [{sent}] {verdict}")
            else:
                scores[pname][prodname] = "ERR"
                print("-> ERROR")

    # Print score matrix
    print("\n" + "=" * 60)
    print("SCORE MATRIX")
    print("=" * 60)
    prod_short = ["polaiya99", "dabao29", "xiulk680", "winona198", "hbn149"]
    header = f"{'name':<10}" + "".join(f"|{s:^11}" for s in prod_short)
    print(header)
    print("-" * len(header))
    for i, persona in enumerate(personas):
        pname = persona["name"]
        row = f"{pname:<10}"
        for product in PRODUCTS:
            s = scores[pname].get(product["display"], "?")
            row += f"|{str(s):^11}"
        print(row)

    # Statistics
    print("\n-- Stats --")
    all_scores = [v for pscores in scores.values() for v in pscores.values() if isinstance(v, int)]
    if all_scores:
        avg = sum(all_scores) / len(all_scores)
        dist = {i: all_scores.count(i) for i in range(1, 6)}
        purchase = sum(1 for s in all_scores if s >= 4)
        print(f"Average: {avg:.2f}")
        print(f"Distribution: {dist}")
        print(f"Purchase rate (>=4): {purchase}/{len(all_scores)} = {purchase/len(all_scores)*100:.1f}%")

        # Per-persona stats
        print("\n-- Per Persona --")
        for persona in personas:
            pname = persona["name"]
            pscores = [v for v in scores[pname].values() if isinstance(v, int)]
            if pscores:
                pavg = sum(pscores) / len(pscores)
                ppurchase = sum(1 for s in pscores if s >= 4)
                print(f"  {pname}: avg={pavg:.1f}, purchase={ppurchase}/{len(pscores)}")

    # -- Phase 2: Context Card Test --
    # -- Phase 1.5: Liu Xiao male product test --
    print("\n" + "=" * 60)
    print("PHASE 1.5: Male Product Test for Liu Xiao")
    print("=" * 60)
    male_product = {
        "name": "loreal_men_oil",
        "display": "欧莱雅男士控油炭爽洁面膏",
        "brand": "欧莱雅男士",
        "price": 79,
        "description": "男士专研控油配方，含火山矿物+活性炭，深层清洁控油，洗后清爽不紧绷。京东男士洁面销量榜Top3，4.9分好评。一步搞定清洁控油。",
        "selling_point": "男士控油，一步清爽",
        "target_audience": "18-35岁油性皮肤男性",
    }
    liu_xiao = personas[4]
    print(f"  {liu_xiao['name']} x {male_product['display']} (RMB{male_product['price']})...", end=" ", flush=True)
    result = await run_single_test(client, endpoint_id, liu_xiao, male_product)
    if result:
        score = result.get("overall_intent", "?")
        sent = result.get("sentiment", "?")
        verdict = result.get("one_sentence_verdict", "")
        summary = result.get("summary_comment", "")
        print(f"-> {score} [{sent}] {verdict}")
        print(f"    Summary: {summary}")

    print("\n" + "=" * 60)
    print("PHASE 2: Context Card Test")
    print("=" * 60)

    test_personas = [personas[1], personas[3]]  # chentingting + wangjiayi
    test_product = PRODUCTS[0]  # polaiya 99

    for persona in test_personas:
        pname = persona["name"]
        print(f"\n  {pname} x {test_product['display']}:")
        for ctx_name, ctx_text in CONTEXT_CARDS.items():
            print(f"    [{ctx_name}]...", end=" ", flush=True)
            result = await run_single_test(
                client, endpoint_id, persona, test_product, ctx_text
            )
            if result:
                score = result.get("overall_intent", "?")
                sent = result.get("sentiment", "?")
                verdict = result.get("one_sentence_verdict", "")
                print(f"-> {score} [{sent}] {verdict}")
            else:
                print("-> ERROR")

    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
