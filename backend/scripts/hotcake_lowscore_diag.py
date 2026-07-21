"""One-off diagnostic: do hot-selling products get systematically low scores?

5 real hot products (P1-P5) + 3 constructed mediocre products (N1-N3),
each scored by 10 real seed personas answering a real 30-question survey.

In-memory direct path: render_prompt + client.complete_json_with_usage
(same prompts the production adapters build), no DB needed.

Usage:
    cd backend
    uv run python scripts/hotcake_lowscore_diag.py            # P1 only (real-score gate)
    uv run python scripts/hotcake_lowscore_diag.py --full     # all 8 products
"""

from __future__ import annotations

import argparse
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
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///tmp_test.db")

from app.ai.factory import get_ai_client  # noqa: E402
from app.ai.json_utils import parse_json_response  # noqa: E402
from app.ai.models import ModelRouter, TaskType  # noqa: E402
from app.ai.prompt_manager import render_prompt  # noqa: E402

PERSONAS_DIR = BACKEND_ROOT.parent / "docs" / "SEEDS" / "personas_v2"
OUTPUT_DIR = BACKEND_ROOT / "tmp"

# 10 personas covering different archetypes (6 critical + 4 normal)
PERSONA_IDS = [1, 2, 3, 6, 9, 11, 12, 17, 19, 24]


def load_personas() -> list[dict]:
    out = []
    for pid in PERSONA_IDS:
        f = PERSONAS_DIR / f"persona_beauty_{pid:03d}.json"
        out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


# ============================================================================
# Product cards (护肤精华/面霜, same category to control for it)
# Fields aligned to ProductAiSummary schema usage in structured_generation.py
# ============================================================================

PRODUCTS: list[dict] = [
    # ---- 正样本: 公认爆品 ----
    {
        "id": "P1_proya_ruby",
        "label": "P1 珀莱雅红宝石精华2.0",
        "name": "珀莱雅红宝石精华2.0",
        "brand": "珀莱雅（PROYA）",
        "category": "护肤",
        "sub_category": "精华",
        "price": 269,
        "price_range": "200-300",
        "target_channel": "ec",
        "main_selling_points": ["六胜肽抗老紧致", "A醇衍生物淡纹", "国货抗老精华销冠"],
        "key_ingredients": ["环肽-161（六胜肽）", "A醇衍生物（视黄醇丙酸酯）", "麦角硫因", "γ-氨基丁酸"],
        "claims_detected": ["抗老紧致", "淡化细纹", "提升肌肤弹性"],
        "risk_or_uncertainty_points": ["A醇类需建立耐受", "孕期慎用"],
        "suitable_skin_types": ["初老肌", "熟龄肌", "大部分肤质"],
        "usage_scenarios": ["夜间抗老护理", "日常紧致精华"],
        "target_audience": "25-40岁关注抗初老/紧致的女性",
        "competitive_position": "国货抗老精华销量冠军，天猫双11精华榜TOP，对标进口抗老精华平价替代。",
        "description": "珀莱雅红宝石精华2.0，六胜肽+A醇衍生物，主打抗老紧致淡纹。269元/30ml。国货抗老精华销冠。",
        "confidence": 0.9,
        "positive": True,
    },
    {
        "id": "P2_winona_cream",
        "label": "P2 薇诺娜舒敏保湿特护霜",
        "name": "薇诺娜舒敏保湿特护霜",
        "brand": "薇诺娜（WINONA）",
        "category": "护肤",
        "sub_category": "面霜",
        "price": 268,
        "price_range": "200-300",
        "target_channel": "ec",
        "main_selling_points": ["敏感肌屏障修护", "皮肤科医生推荐", "舒缓泛红"],
        "key_ingredients": ["青刺果油", "马齿苋提取物", "透明质酸钠"],
        "claims_detected": ["修护皮肤屏障", "舒缓敏感", "深层保湿", "临床验证"],
        "risk_or_uncertainty_points": ["大油皮可能偏厚重", "活性成分浓度未公开"],
        "suitable_skin_types": ["敏感肌", "干性肌", "痘敏肌", "医美术后"],
        "usage_scenarios": ["换季敏感急救", "医美术后修护", "日常保湿"],
        "target_audience": "敏感肌、干皮人群，18-45岁",
        "competitive_position": "国货敏感肌龙头品牌，皮肤科背书，天猫舒敏面霜TOP1，对标雅漾理肤泉。",
        "description": "薇诺娜舒敏保湿特护霜，青刺果油+马齿苋，舒缓修护敏感肌屏障。268元/50g。敏感肌龙头爆品。",
        "confidence": 0.92,
        "positive": True,
    },
    {
        "id": "P3_sulwhasoo",
        "label": "P3 雪花秀润燥精华",
        "name": "雪花秀润燥精华",
        "brand": "雪花秀（Sulwhasoo）",
        "category": "护肤",
        "sub_category": "精华",
        "price": 850,
        "price_range": "800-1000",
        "target_channel": "ec",
        "main_selling_points": ["韩方人参滋养抗老", "高端滋阴丹配方", "高端常青爆品"],
        "key_ingredients": ["人参根提取物", "滋阴丹复合物", "蜂蜜提取物"],
        "claims_detected": ["滋养抗老", "改善暗沉", "提升光泽"],
        "risk_or_uncertainty_points": ["价格门槛高", "质地偏滋润，油皮夏季可能厚重"],
        "suitable_skin_types": ["熟龄肌", "干性肌", "需滋养抗老人群"],
        "usage_scenarios": ["高端抗老护理", "秋冬滋养"],
        "target_audience": "30-50岁中高收入女性，追求高端抗老滋养",
        "competitive_position": "韩系高端护肤标杆，常青爆品，对标兰蔻雅诗兰黛高端线。",
        "description": "雪花秀润燥精华，韩方人参+滋阴丹，高端抗老滋养。850元/50ml。高端常青爆品。",
        "confidence": 0.88,
        "positive": True,
    },
    {
        "id": "P4_lancome_genifique",
        "label": "P4 兰蔻小黑瓶精华肌底液",
        "name": "兰蔻小黑瓶精华肌底液",
        "brand": "兰蔻（Lancome）",
        "category": "护肤",
        "sub_category": "精华",
        "price": 1080,
        "price_range": "1000-1200",
        "target_channel": "ec",
        "main_selling_points": ["二裂酵母发酵修护", "稳定肌底", "进口精华常青爆品"],
        "key_ingredients": ["二裂酵母发酵产物溶胞物", "透明质酸", "腺苷"],
        "claims_detected": ["修护肌底", "稳定肌肤状态", "提升后续吸收"],
        "risk_or_uncertainty_points": ["价格高", "功效偏维稳，抗老效果因人而异"],
        "suitable_skin_types": ["所有肤质", "需修护维稳人群"],
        "usage_scenarios": ["精华前打底", "日常肌底护理"],
        "target_audience": "25-45岁中高收入女性",
        "competitive_position": "进口精华肌底液常青爆品，全球畅销，对标雅诗兰黛小棕瓶。",
        "description": "兰蔻小黑瓶精华肌底液，二裂酵母发酵产物，修护稳定肌底。1080元/50ml。进口精华常青爆品。",
        "confidence": 0.9,
        "positive": True,
    },
    {
        "id": "P5_skinceuticals_ce",
        "label": "P5 修丽可CE复合修护精华",
        "name": "修丽可CE复合修护精华",
        "brand": "修丽可（SkinCeuticals）",
        "category": "护肤",
        "sub_category": "精华",
        "price": 1280,
        "price_range": "1200-1500",
        "target_channel": "ec",
        "main_selling_points": ["15%VC黄金抗氧化", "杜克大学专利配方", "临床数据背书"],
        "key_ingredients": ["15%左旋维生素C", "1%维生素E", "0.5%阿魏酸"],
        "claims_detected": ["抗氧化", "抗光老化", "提亮淡斑", "临床验证"],
        "risk_or_uncertainty_points": ["质地偏油需建立耐受", "开封后易氧化", "价格高"],
        "suitable_skin_types": ["成分党", "抗老抗氧需求人群", "耐受性皮肤"],
        "usage_scenarios": ["白天抗氧化打底", "抗光老化护理"],
        "target_audience": "成分党、高预算护肤爱好者，25-45岁",
        "competitive_position": "高端抗氧精华标杆，杜克专利+多项临床数据，对标各家VC精华天花板。",
        "description": "修丽可CE复合修护精华，15%VC+1%VE+0.5%阿魏酸，抗氧化抗老。1280元/30ml。高端抗氧爆品。",
        "confidence": 0.93,
        "positive": True,
    },
    # ---- 负样本: 构造的明显平庸品 ----
    {
        "id": "N1_shuirunyuan",
        "label": "N1 水润源保湿精华",
        "name": "\"水润源\"保湿精华",
        "brand": "水润源（无名品牌）",
        "category": "护肤",
        "sub_category": "精华",
        "price": 199,
        "price_range": "150-200",
        "target_channel": "ec",
        "main_selling_points": ["基础保湿", "清爽好吸收"],
        "key_ingredients": ["水", "甘油", "丁二醇"],
        "claims_detected": ["保湿补水"],
        "risk_or_uncertainty_points": ["无任何活性成分", "无功效差异化", "成分极其基础", "品牌无知名度"],
        "suitable_skin_types": ["所有肤质"],
        "usage_scenarios": ["日常基础保湿"],
        "target_audience": "对成分无要求的大众消费者",
        "competitive_position": "无名品牌，仅基础保湿成分，无活性物、无差异化，同价位可选项极多。",
        "description": "\"水润源\"保湿精华，仅含水/甘油/丁二醇，基础保湿，无活性物、无差异化。199元/30ml。",
        "confidence": 0.5,
        "positive": False,
    },
    {
        "id": "N2_huanyan",
        "label": "N2 焕颜美白精华",
        "name": "\"焕颜\"美白精华",
        "brand": "焕颜（杂牌）",
        "category": "护肤",
        "sub_category": "精华",
        "price": 159,
        "price_range": "150-200",
        "target_channel": "ec",
        "main_selling_points": ["宣称美白提亮"],
        "key_ingredients": ["烟酰胺（浓度不明）", "香精", "水", "酒精"],
        "claims_detected": ["美白", "提亮肤色"],
        "risk_or_uncertainty_points": [
            "烟酰胺浓度不公开/含糊",
            "含香精易致敏",
            "包装粗糙廉价",
            "品牌为杂牌无背书",
            "美白宣称无数据支撑",
        ],
        "suitable_skin_types": ["油性肌（但含香精慎用）"],
        "usage_scenarios": ["日常美白（存疑）"],
        "target_audience": "被美白概念吸引的低价消费者",
        "competitive_position": "杂牌，美白宣称含糊，烟酰胺浓度不明、含香精、包装粗糙，可信度低。",
        "description": "\"焕颜\"美白精华，宣称美白但烟酰胺浓度不明，含香精，包装粗糙。159元/30ml。杂牌。",
        "confidence": 0.45,
        "positive": False,
    },
    {
        "id": "N3_zhicuiyuan",
        "label": "N3 植萃源抗老精华",
        "name": "\"植萃源\"抗老精华",
        "brand": "植萃源（小众）",
        "category": "护肤",
        "sub_category": "精华",
        "price": 329,
        "price_range": "300-400",
        "target_channel": "ec",
        "main_selling_points": ["植物抗老（模糊宣称）"],
        "key_ingredients": ["多种植物提取物（无浓度）"],
        "claims_detected": ["抗老", "紧致（无数据）"],
        "risk_or_uncertainty_points": [
            "仅模糊'植物抗老'宣称",
            "无任何活性物浓度标注",
            "无功效数据/临床支撑",
            "小众品牌无背书",
            "定价偏高与价值不符",
        ],
        "suitable_skin_types": ["宣称所有肤质"],
        "usage_scenarios": ["抗老护理（存疑）"],
        "target_audience": "被'天然植物'概念吸引的消费者",
        "competitive_position": "小众品牌，模糊植物抗老宣称，无浓度无数据，329元定价与可证实价值不符。",
        "description": "\"植萃源\"抗老精华，模糊'植物抗老'宣称，无活性物浓度、无功效数据。329元/30ml。小众。",
        "confidence": 0.4,
        "positive": False,
    },
]


def product_summary(p: dict) -> dict:
    """Strip diag-only keys; keep schema-aligned fields for the prompt."""
    return {k: v for k, v in p.items() if k not in ("label", "positive")}


async def generate_survey(client, endpoint_id: str, product: dict) -> list[dict] | None:
    """Real 30-question survey via the same two-batch path as the adapter.

    SurveyGenerationAdapter generates 2 parallel batches of 15. We replicate
    that here with render_prompt(batch=1/2). Max 1 retry per batch.
    """
    from app.ai.adapters.structured_generation import SURVEY_BATCH_DIMS

    async def one_batch(batch: int) -> list[dict] | None:
        prompt, _, _ = render_prompt(
            "survey_generate",
            user_role_type="manufacturer",
            product_ai_summary=product_summary(product),
            extra_focus="",
            product={"id": product["id"]},
            batch=batch,
        )
        for attempt in range(2):  # initial + 1 retry
            try:
                raw = await client.complete_json(
                    system="你是专业的市场调研问卷设计专家。严格按 JSON schema 输出。",
                    user=prompt,
                    endpoint_id=endpoint_id,
                )
                data = parse_json_response(raw)
                qs = data.get("questions") if isinstance(data, dict) else None
                if qs and isinstance(qs, list) and len(qs) >= 10:
                    return qs
                print(f"    [survey b{batch}] attempt {attempt+1}: bad shape, "
                      f"got {len(qs) if qs else 0}")
            except Exception as e:
                print(f"    [survey b{batch}] attempt {attempt+1} failed: {e}")
        return None

    b1, b2 = await asyncio.gather(one_batch(1), one_batch(2))
    if b1 is None or b2 is None:
        return None
    merged = (b1 + b2)
    for i, q in enumerate(merged, 1):
        q["id"] = f"q{i:02d}"
    return merged


async def run_persona_answer(
    client, endpoint_id: str, persona: dict, product: dict,
    questions: list[dict], sem: asyncio.Semaphore,
) -> dict | None:
    """One persona answers the survey. Returns dict with intent/sentiment/usage.

    Uses complete_json_with_usage so we can prove real (token>0) vs mock.
    Max 1 retry.
    """
    prompt, _, _ = render_prompt(
        "persona_answer",
        persona=persona,
        product_ai_summary=product_summary(product),
        survey_questions=questions,
    )
    async with sem:
        for attempt in range(2):  # initial + 1 retry
            try:
                res = await client.complete_json_with_usage(
                    system="你是一名真实的中国消费者，正在参与产品测评问卷。",
                    user=prompt,
                    endpoint_id=endpoint_id,
                )
                data = parse_json_response(res.content)
                if data and data.get("answers") is not None and "overall_intent" in data:
                    raw_intent = data["overall_intent"]
                    intent = max(1, min(5, int(raw_intent)))
                    sent = str(data.get("sentiment", "neutral"))
                    if sent not in ("positive", "neutral", "negative"):
                        sent = "neutral"
                    return {
                        "overall_intent": intent,
                        "sentiment": sent,
                        "in_tokens": res.usage.input_tokens,
                        "out_tokens": res.usage.output_tokens,
                        "verdict": data.get("one_sentence_verdict", ""),
                    }
                print(f"    [{persona['name']}] attempt {attempt+1}: missing keys")
            except Exception as e:
                print(f"    [{persona['name']}] attempt {attempt+1} failed: {e}")
        return None


async def run_product(client, survey_ep, answer_ep, product, personas, sem):
    print(f"\n{'='*70}\n{product['label']}  (¥{product['price']})\n{'='*70}")
    questions = await generate_survey(client, survey_ep, product)
    if not questions:
        print(f"  FATAL: survey generation failed for {product['label']}")
        return None
    print(f"  survey: {len(questions)} questions generated")

    results: dict[str, dict | None] = {}

    async def one(persona):
        r = await run_persona_answer(
            client, answer_ep, persona, product, questions, sem,
        )
        results[persona["name"]] = r
        if r:
            print(f"  {persona['name']:<6} -> intent={r['overall_intent']} "
                  f"[{r['sentiment']}] tok={r['in_tokens']}+{r['out_tokens']}")
        else:
            print(f"  {persona['name']:<6} -> FAIL")

    await asyncio.gather(*[one(p) for p in personas])
    return {"product": product, "questions": questions, "results": results}


def summarize(bundle) -> dict:
    p = bundle["product"]
    res = bundle["results"]
    intents = [r["overall_intent"] for r in res.values() if r]
    sent = {"positive": 0, "neutral": 0, "negative": 0}
    for r in res.values():
        if r:
            sent[r["sentiment"]] += 1
    avg = sum(intents) / len(intents) if intents else 0.0
    return {
        "id": p["id"], "label": p["label"], "positive": p["positive"],
        "intents": intents, "avg": round(avg, 1), "sentiment": sent,
        "n": len(intents),
    }


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true",
                        help="run all 8 products (default: P1 only as real-score gate)")
    parser.add_argument("--concurrency", type=int, default=5)
    args, _ = parser.parse_known_args()

    personas = load_personas()
    client = get_ai_client()
    router = ModelRouter()
    survey_ep = router.get(TaskType.SURVEY_GENERATE).endpoint_id
    answer_ep = router.get(TaskType.PERSONA_ANSWER).endpoint_id
    sem = asyncio.Semaphore(args.concurrency)

    print(f"AI Provider: {os.environ.get('AI_PROVIDER')}")
    print(f"Client class: {type(client).__name__}")
    print(f"Survey endpoint: {survey_ep}")
    print(f"Answer endpoint: {answer_ep}")
    print(f"Personas ({len(personas)}): "
          f"{[(p['name'], 'CRIT' if p.get('is_critical') else 'norm') for p in personas]}")

    products = PRODUCTS if args.full else PRODUCTS[:1]
    bundles = []
    for prod in products:
        b = await run_product(client, survey_ep, answer_ep, prod, personas, sem)
        bundles.append(b)

    # Gate check on P1
    if bundles and bundles[0]:
        res = bundles[0]["results"]
        toks = [r["in_tokens"] + r["out_tokens"] for r in res.values() if r]
        print(f"\n{'#'*70}\nREAL-SCORE GATE (P1)\n{'#'*70}")
        print(f"  successful personas: {len([r for r in res.values() if r])}/{len(personas)}")
        print(f"  token totals per persona: {toks}")
        print(f"  all token>0: {all(t > 0 for t in toks) if toks else False}")
        intents = [r['overall_intent'] for r in res.values() if r]
        print(f"  intents: {intents}  (mock would be uniform 3/4 with tok=0)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summaries = [summarize(b) for b in bundles if b]
    out = {
        "summaries": summaries,
        "raw": [{"id": b["product"]["id"],
                 "results": b["results"],
                 "n_questions": len(b["questions"])} for b in bundles if b],
    }
    (OUTPUT_DIR / "hotcake_lowscore_diag.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*70}\nSUMMARY TABLE\n{'='*70}")
    print(f"{'product':<32}{'n':>3}{'avg':>6}  intents / sentiment")
    for s in summaries:
        print(f"{s['label']:<32}{s['n']:>3}{s['avg']:>6}  "
              f"{s['intents']}  "
              f"pos/neu/neg={s['sentiment']['positive']}/"
              f"{s['sentiment']['neutral']}/{s['sentiment']['negative']}")

    if args.full and len(summaries) == 8:
        pos = [s for s in summaries if s["positive"]]
        neg = [s for s in summaries if not s["positive"]]
        pos_avg = sum(s["avg"] for s in pos) / len(pos)
        neg_avg = sum(s["avg"] for s in neg) / len(neg)
        print(f"\n  爆品(P1-P5) 均分均值: {pos_avg:.2f}")
        print(f"  平庸品(N1-N3) 均分均值: {neg_avg:.2f}")
        print(f"  爆品落在2.x-3.x区间的: "
              f"{[s['label'][:6] for s in pos if 2 <= s['avg'] < 4]}")
        worst_pos = min(s["avg"] for s in pos)
        best_neg = max(s["avg"] for s in neg)
        print(f"  最低爆品均分={worst_pos}  最高平庸品均分={best_neg}  "
              f"倒挂(爆品<=平庸品)={worst_pos <= best_neg}")

    print(f"\nsaved: {OUTPUT_DIR / 'hotcake_lowscore_diag.json'}")


if __name__ == "__main__":
    asyncio.run(main())
