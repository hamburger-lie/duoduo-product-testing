"""One-shot diagnostic: do hit products get systematically low scores?

Hypothesis under test: the current scoring engine systematically scores
well-known "hit" skincare products in the low band (2.x-3.x), even below
deliberately mediocre control products.

Method (light, no DB):
- Build 8 product summaries (5 hits + 3 mediocre controls) as plain dicts that
  match ProductAiSummary fields used by the prompts.
- For each product, generate a REAL 30-question survey via the
  survey_generate prompt (same prompt SurveyGenerationAdapter uses), with one
  retry; fall back to a fixed generic serum survey only if generation fails.
- Load 10 real seed personas (personas_v2), mix of is_critical true/false.
- For each (product, persona) call render_prompt("persona_answer", ...) +
  client.complete_json_with_usage() — same path PersonaAnswerGenerationAdapter
  uses internally — capturing overall_intent, sentiment, and token usage.

Anti-fake-score guard: run P1 alone first, assert usage.total_tokens > 0 and
the response is not the mock {"mock": true} stub. Abort if mock/unreachable.

Usage:
    cd backend
    uv run python scripts/hitproduct_lowscore_diag.py
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("AI_PROVIDER", "deepseek")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///tmp_diag.db")

from app.ai.factory import get_ai_client  # noqa: E402
from app.ai.json_utils import parse_json_response  # noqa: E402
from app.ai.models import ModelRouter, TaskType  # noqa: E402
from app.ai.prompt_manager import render_prompt  # noqa: E402

PERSONAS_DIR = BACKEND_ROOT.parent / "docs" / "SEEDS" / "personas_v2"
# 10 personas: 7 critical + 3 non-critical, ages 19-45, varied archetypes.
PERSONA_IDS = [1, 3, 5, 6, 8, 9, 10, 15, 18, 20]


def load_personas() -> list[dict]:
    out = []
    for pid in PERSONA_IDS:
        f = PERSONAS_DIR / f"persona_beauty_{pid:03d}.json"
        with open(f, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


# ---------------------------------------------------------------------------
# 8 product summaries (fields aligned to ProductAiSummary usage in the prompts)
# ---------------------------------------------------------------------------
PRODUCTS: list[dict] = [
    {
        "id": "P1_proya_ruby",
        "name": "珀莱雅红宝石精华2.0",
        "brand": "珀莱雅",
        "category": "护肤",
        "sub_category": "精华",
        "price": 269.0,
        "price_range": "200-300",
        "target_channel": "ec",
        "main_selling_points": ["六胜肽+A醇衍生物抗老紧致", "淡化细纹", "国货抗老精华销冠"],
        "key_ingredients": ["环六肽-9（六胜肽）", "视黄醇丙酸酯（A醇衍生物）", "麦角硫因"],
        "claims_detected": ["抗老紧致", "淡纹", "提拉紧致"],
        "suitable_skin_types": ["初老肌", "混合肌", "中性肌"],
        "target_audience": "25-40岁关注抗初老的女性",
        "competitive_position": "国货抗老精华销量冠军，天猫精华榜常年前列，对标进口抗老精华平价替代。",
        "risk_or_uncertainty_points": ["A醇衍生物需建立耐受", "敏感肌可能轻微刺激"],
        "description": "珀莱雅红宝石精华2.0，六胜肽+A醇衍生物双抗老体系，主打紧致淡纹，269元/30ml。国货抗老精华销冠，小红书爆款。",
        "confidence": 0.9,
    },
    {
        "id": "P2_winona_cream",
        "name": "薇诺娜舒敏保湿特护霜",
        "brand": "薇诺娜",
        "category": "护肤",
        "sub_category": "面霜",
        "price": 268.0,
        "price_range": "250-300",
        "target_channel": "ec",
        "main_selling_points": ["青刺果油+马齿苋舒缓修护", "敏感肌屏障修护", "皮肤科医生推荐"],
        "key_ingredients": ["青刺果油", "马齿苋提取物", "双分子透明质酸钠"],
        "claims_detected": ["修护屏障", "舒缓敏感泛红", "临床验证"],
        "suitable_skin_types": ["敏感肌", "干皮", "痘敏肌"],
        "target_audience": "敏感肌、干皮、医美术后修护人群",
        "competitive_position": "国货敏感肌龙头爆品，天猫舒敏面霜TOP1，对标雅漾、理肤泉。",
        "risk_or_uncertainty_points": ["活性成分浓度未公开", "大油皮可能闷痘"],
        "description": "薇诺娜舒敏保湿特护霜，青刺果油+马齿苋舒缓修护敏感肌屏障，268元/50g。敏感肌龙头爆品，皮肤科背书。",
        "confidence": 0.9,
    },
    {
        "id": "P3_sulwhasoo",
        "name": "雪花秀润燥精华",
        "brand": "雪花秀",
        "category": "护肤",
        "sub_category": "精华",
        "price": 850.0,
        "price_range": "800-900",
        "target_channel": "ec",
        "main_selling_points": ["韩方人参+滋阴丹", "高端抗老滋养", "高端常青爆品"],
        "key_ingredients": ["人参提取物", "滋阴丹复方草本精萃"],
        "claims_detected": ["滋养抗老", "改善暗沉", "紧致饱满"],
        "suitable_skin_types": ["干皮", "熟龄肌", "暗沉肌"],
        "target_audience": "30-50岁追求高端滋养抗老的女性",
        "competitive_position": "高端韩妆常青爆品，雪花秀招牌精华之一，对标兰蔻、海蓝之谜。",
        "risk_or_uncertainty_points": ["价格门槛高", "草本香味部分人不适应", "活性物浓度未公开"],
        "description": "雪花秀润燥精华，韩方人参+滋阴丹高端抗老滋养，850元/50ml。高端常青爆品。",
        "confidence": 0.88,
    },
    {
        "id": "P4_lancome_genifique",
        "name": "兰蔻小黑瓶精华肌底液",
        "brand": "兰蔻",
        "category": "护肤",
        "sub_category": "精华",
        "price": 1080.0,
        "price_range": "1000-1200",
        "target_channel": "ec",
        "main_selling_points": ["二裂酵母发酵产物", "修护稳定肌底", "进口精华常青爆品"],
        "key_ingredients": ["二裂酵母发酵产物溶胞物", "透明质酸"],
        "claims_detected": ["修护肌底", "稳定提亮", "增强吸收"],
        "suitable_skin_types": ["所有肤质", "初老肌", "暗沉肌"],
        "target_audience": "25-45岁追求肌底修护的中高收入女性",
        "competitive_position": "进口精华常青爆品，兰蔻招牌肌底液，全球热销，天猫精华榜常年TOP。",
        "risk_or_uncertainty_points": ["价格门槛高", "发酵成分功效因人而异"],
        "description": "兰蔻小黑瓶精华肌底液，二裂酵母发酵产物修护稳定肌底，1080元/50ml。进口精华常青爆品。",
        "confidence": 0.9,
    },
    {
        "id": "P5_skinceuticals_ce",
        "name": "修丽可CE复合修护精华",
        "brand": "修丽可",
        "category": "护肤",
        "sub_category": "精华",
        "price": 1280.0,
        "price_range": "1200-1400",
        "target_channel": "ec",
        "main_selling_points": ["15%VC+1%VE+0.5%阿魏酸", "抗氧化抗老", "高端抗氧爆品"],
        "key_ingredients": ["15%左旋维生素C", "1%维生素E", "0.5%阿魏酸"],
        "claims_detected": ["抗氧化", "抗光老化", "提亮淡纹", "临床数据支持"],
        "suitable_skin_types": ["成分党", "初老肌", "暗沉肌（需建立耐受）"],
        "target_audience": "成分党、高预算抗老护肤爱好者",
        "competitive_position": "高端抗氧爆品，Duke专利黄金比例配方，有临床数据背书，抗氧精华标杆。",
        "risk_or_uncertainty_points": ["价格高", "质地偏油需耐受", "开封后易氧化"],
        "description": "修丽可CE复合修护精华，15%VC+1%VE+0.5%阿魏酸专利配方抗氧化抗老，1280元/30ml。高端抗氧爆品，临床数据背书。",
        "confidence": 0.92,
    },
    # ---- 负样本：构造的明显平庸品，应低分 ----
    {
        "id": "N1_shuirunyuan",
        "name": "“水润源”保湿精华",
        "brand": "水润源",
        "category": "护肤",
        "sub_category": "精华",
        "price": 199.0,
        "price_range": "150-200",
        "target_channel": "ec",
        "main_selling_points": ["基础保湿", "清爽不黏腻"],
        "key_ingredients": ["水", "甘油", "丁二醇"],
        "claims_detected": ["保湿补水"],
        "suitable_skin_types": ["所有肤质"],
        "target_audience": "追求基础保湿的大众消费者",
        "competitive_position": "无名品牌，无差异化卖点，配方仅基础保湿成分，无活性物。",
        "risk_or_uncertainty_points": ["无任何活性成分", "无功效数据", "无品牌口碑", "199元定价偏高"],
        "description": "“水润源”保湿精华，配方仅含水、甘油、丁二醇等基础保湿成分，无活性物、无差异化卖点，199元/30ml。无名品牌。",
        "confidence": 0.4,
    },
    {
        "id": "N2_huanyan",
        "name": "“焕颜”美白精华",
        "brand": "焕颜",
        "category": "护肤",
        "sub_category": "精华",
        "price": 159.0,
        "price_range": "150-200",
        "target_channel": "ec",
        "main_selling_points": ["宣称美白", "提亮肤色"],
        "key_ingredients": ["烟酰胺（浓度不明）", "香精", "水", "甘油"],
        "claims_detected": ["美白", "提亮"],
        "suitable_skin_types": ["所有肤质"],
        "target_audience": "想美白的价格敏感消费者",
        "competitive_position": "杂牌，宣称美白但烟酰胺浓度不明，含香精，包装粗糙，无功效数据。",
        "risk_or_uncertainty_points": ["烟酰胺浓度不公开", "含香精易致敏", "包装粗糙", "无品牌背书", "美白宣称无数据"],
        "description": "“焕颜”美白精华，宣称美白但烟酰胺浓度不明，含香精，包装粗糙，159元/30ml。杂牌，无功效数据。",
        "confidence": 0.35,
    },
    {
        "id": "N3_zhicuiyuan",
        "name": "“植萃源”抗老精华",
        "brand": "植萃源",
        "category": "护肤",
        "sub_category": "精华",
        "price": 329.0,
        "price_range": "300-350",
        "target_channel": "ec",
        "main_selling_points": ["植物抗老", "天然温和"],
        "key_ingredients": ["多种植物提取物（浓度不明）"],
        "claims_detected": ["抗老", "紧致"],
        "suitable_skin_types": ["所有肤质"],
        "target_audience": "偏好天然植物概念的抗老人群",
        "competitive_position": "小众品牌，模糊“植物抗老”宣称，无活性物浓度、无功效数据，概念堆砌。",
        "risk_or_uncertainty_points": ["无活性物浓度", "无功效数据", "纯概念宣称", "329元定价虚高", "无品牌口碑"],
        "description": "“植萃源”抗老精华，模糊“植物抗老”宣称，无活性物浓度、无功效数据，329元/30ml。小众品牌，概念堆砌。",
        "confidence": 0.35,
    },
]

# Fixed fallback survey (generic serum), used only if survey_generate fails.
FALLBACK_SURVEY = [
    {"id": "q01", "dim": "first_impression", "type": "open", "question": "看到这个产品的第一印象是什么？"},
    {"id": "q02", "dim": "purchase_motivation", "type": "scale_1_5", "question": "你对这个产品的兴趣程度（1-5）？"},
    {"id": "q03", "dim": "purchase_motivation", "type": "open", "question": "最吸引你或最让你犹豫的点是什么？"},
    {"id": "q04", "dim": "price_sensitivity", "type": "single", "question": "你觉得这个价格如何？",
     "options": ["太贵不会买", "有点贵但能接受", "价格合理", "很划算", "太便宜不放心"]},
    {"id": "q05", "dim": "competitor_comparison", "type": "open", "question": "和你熟悉的同类产品相比，你怎么看它？"},
    {"id": "q06", "dim": "repurchase_intent", "type": "single", "question": "你会购买这个产品吗？",
     "options": ["一定不会买", "可能不会买", "要看情况", "很可能会买", "一定会买"]},
]


async def generate_survey(client, endpoint_id: str, product: dict) -> tuple[list[dict], str]:
    """Generate a real 30-q survey (1 retry). Return (questions, source_label)."""
    rendered, _, _ = render_prompt(
        "survey_generate",
        product_ai_summary=product,
        user_role_type="manufacturer",
        extra_focus="",
        product={"id": product["id"]},
    )
    for attempt in range(2):  # initial + 1 retry
        try:
            raw = await client.complete_json(
                system="你是专业的市场调研问卷设计专家。严格按 JSON schema 输出。",
                user=rendered,
                endpoint_id=endpoint_id,
            )
            data = parse_json_response(raw)
            qs = data.get("questions", []) if isinstance(data, dict) else []
            if qs:
                return qs, f"AI生成({len(qs)}题)"
        except Exception as e:  # noqa: BLE001
            print(f"    [survey] {product['id']} attempt {attempt+1} failed: {e}")
        if attempt == 0:
            await asyncio.sleep(2)
    print(f"    [survey] {product['id']} -> FALLBACK fixed survey")
    return FALLBACK_SURVEY, "固定兜底问卷"


async def run_persona(client, endpoint_id, persona, product, questions):
    """One persona answer. Return dict with intent/sentiment/usage or None."""
    rendered, _, _ = render_prompt(
        "persona_answer",
        persona=persona,
        product_ai_summary=product,
        survey_questions=questions,
    )
    for attempt in range(2):  # initial + 1 retry, per budget
        try:
            res = await client.complete_json_with_usage(
                system="你是一名真实的中国消费者，正在参与产品测评问卷。",
                user=rendered,
                endpoint_id=endpoint_id,
            )
            data = parse_json_response(res.content)
            intent = data.get("overall_intent")
            sentiment = data.get("sentiment", "neutral")
            if isinstance(intent, (int, float)):
                return {
                    "intent": max(1, min(5, int(intent))),
                    "sentiment": sentiment if sentiment in ("positive", "neutral", "negative") else "neutral",
                    "total_tokens": res.usage.total_tokens,
                    "is_mock": '"mock"' in res.content and "overall_intent" not in res.content,
                    "raw_keys": list(data.keys())[:6],
                }
            print(f"      [{persona['name']}] attempt {attempt+1}: no numeric overall_intent")
        except Exception as e:  # noqa: BLE001
            print(f"      [{persona['name']}] attempt {attempt+1} failed: {e}")
        if attempt == 0:
            await asyncio.sleep(2)
    return None


async def main() -> None:
    personas = load_personas()
    client = get_ai_client()
    router = ModelRouter()
    survey_ep = router.get(TaskType.SURVEY_GENERATE).endpoint_id
    answer_ep = router.get(TaskType.PERSONA_ANSWER).endpoint_id

    print(f"AI_PROVIDER={os.environ.get('AI_PROVIDER')}  client={type(client).__name__}")
    print(f"survey_endpoint={survey_ep}  answer_endpoint={answer_ep}")
    print(f"Personas (10): " + ", ".join(
        f"{p['name']}(crit={p['is_critical']})" for p in personas))
    print()

    sem = asyncio.Semaphore(6)

    async def guarded(persona, product, questions):
        async with sem:
            return await run_persona(client, answer_ep, persona, product, questions)

    summaries: dict[str, dict] = {}

    # ----- PHASE 0: P1 only, real-score guard -----
    p1 = PRODUCTS[0]
    print("=" * 70)
    print(f"PHASE 0 — REAL-SCORE GUARD on {p1['id']} ({p1['name']})")
    print("=" * 70)
    qs, src = await generate_survey(client, survey_ep, p1)
    print(f"  survey source: {src}")
    p1_results = await asyncio.gather(*[guarded(p, p1, qs) for p in personas])

    ok = [r for r in p1_results if r]
    if not ok:
        print("\n[ABORT] P1 produced zero valid results — deepseek unreachable or all failed.")
        return
    total_tok = sum(r["total_tokens"] for r in ok)
    any_mock = any(r["is_mock"] for r in ok)
    intents = [r["intent"] for r in ok]
    distinct = len(set(intents))
    print(f"\n  P1 valid={len(ok)}/10  total_tokens={total_tok}  any_mock={any_mock}")
    print(f"  P1 intents={intents}  distinct_values={distinct}")
    print(f"  sample raw_keys: {ok[0]['raw_keys']}")
    if total_tok == 0 or any_mock:
        print("\n[ABORT] Detected MOCK / zero-token output. Not real deepseek. Stopping per anti-fake-score rule.")
        return
    print("\n  [GUARD PASS] total_tokens>0, no mock stub, real deepseek confirmed. Proceeding to remaining 7 products.")
    summaries[p1["id"]] = _summarize(p1, personas, p1_results)

    # ----- PHASE 1: remaining 7 products -----
    for product in PRODUCTS[1:]:
        print("\n" + "=" * 70)
        print(f"PRODUCT {product['id']} — {product['name']} (¥{product['price']})")
        print("=" * 70)
        qs, src = await generate_survey(client, survey_ep, product)
        print(f"  survey source: {src}")
        results = await asyncio.gather(*[guarded(p, product, qs) for p in personas])
        summaries[product["id"]] = _summarize(product, personas, results)

    # ----- FINAL TABLE -----
    _print_final(summaries, personas)


def _summarize(product, personas, results) -> dict:
    rows = []
    intents = []
    sent = {"positive": 0, "neutral": 0, "negative": 0}
    for p, r in zip(personas, results):
        if r:
            rows.append((p["name"], r["intent"], r["sentiment"]))
            intents.append(r["intent"])
            sent[r["sentiment"]] += 1
        else:
            rows.append((p["name"], None, "ERR"))
    avg = round(sum(intents) / len(intents), 1) if intents else None
    return {
        "id": product["id"], "name": product["name"], "price": product["price"],
        "rows": rows, "intents": intents, "avg": avg, "sent": sent,
        "valid": len(intents),
    }


def _print_final(summaries: dict, personas) -> None:
    print("\n\n" + "#" * 70)
    print("# FINAL RESULTS")
    print("#" * 70)
    order = [p["id"] for p in PRODUCTS]
    for pid in order:
        s = summaries.get(pid)
        if not s:
            continue
        print(f"\n[{pid}] {s['name']}  (¥{s['price']})")
        print(f"  intents (n={s['valid']}): {s['intents']}")
        print(f"  AVG = {s['avg']}   sentiment pos/neu/neg = "
              f"{s['sent']['positive']}/{s['sent']['neutral']}/{s['sent']['negative']}")

    print("\n" + "=" * 70)
    print("HIT (P1-P5) vs MEDIOCRE (N1-N3) — average overall_intent")
    print("=" * 70)
    hits = [summaries[p].get("avg") for p in order[:5] if summaries.get(p) and summaries[p]["avg"] is not None]
    meds = [summaries[p].get("avg") for p in order[5:] if summaries.get(p) and summaries[p]["avg"] is not None]
    for pid in order[:5]:
        s = summaries.get(pid)
        if s:
            print(f"  HIT  {pid:<24} avg={s['avg']}")
    for pid in order[5:]:
        s = summaries.get(pid)
        if s:
            print(f"  MED  {pid:<24} avg={s['avg']}")
    if hits and meds:
        hit_mean = round(sum(hits) / len(hits), 2)
        med_mean = round(sum(meds) / len(meds), 2)
        max_med = max(meds)
        inverted = [p for p in order[:5]
                    if summaries.get(p) and summaries[p]["avg"] is not None
                    and summaries[p]["avg"] <= max_med]
        print(f"\n  hit_mean={hit_mean}  mediocre_mean={med_mean}")
        print(f"  hits in low band (<=3.5): "
              f"{[p for p in order[:5] if summaries.get(p) and summaries[p]['avg'] is not None and summaries[p]['avg'] <= 3.5]}")
        print(f"  hits whose avg <= best mediocre ({max_med}): {inverted}")


if __name__ == "__main__":
    asyncio.run(main())
