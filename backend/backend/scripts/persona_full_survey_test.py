"""Complete persona survey test — real AI, full 30-question survey.

Supports single-product or multi-product (parallel) mode.

Usage:
    cd backend
    # Single product
    .venv/Scripts/python.exe scripts/persona_full_survey_test.py --product detailed
    .venv/Scripts/python.exe scripts/persona_full_survey_test.py --product sparse
    # All 5 products in parallel (32 personas each)
    .venv/Scripts/python.exe scripts/persona_full_survey_test.py --product all
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
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


def load_personas(start: int = 1, end: int = 32) -> list[dict]:
    personas = []
    for f in sorted(PERSONAS_DIR.glob("persona_beauty_*.json")):
        num = int(f.stem.split("_")[-1])
        if start <= num <= end:
            with open(f, encoding="utf-8") as fh:
                personas.append(json.load(fh))
    return personas


# ============================================================================
# 产品定义
# ============================================================================

# --- 详细产品 1: 薇诺娜（中端·敏感肌面霜·详细） ---
PRODUCT_WINONA = {
    "id": "winona_detailed",
    "name": "薇诺娜舒敏保湿特护霜（第二代）",
    "brand": "薇诺娜（WINONA）",
    "category": "护肤",
    "sub_category": "面霜",
    "price": 188,
    "price_range": "150-200",
    "target_channel": "ec",
    "main_selling_points": [
        "敏感肌专研修护",
        "皮肤科医生推荐",
        "54家三甲医院临床验证",
        "无香精无防腐剂无酒精无色素",
        "20秒即刻舒缓，7天减少敏感反复",
    ],
    "key_ingredients_or_features": [
        "青刺果油（云南哈巴雪山特有植物，修护皮肤屏障）",
        "马齿苋提取物（舒缓抗炎）",
        "双分子透明质酸钠（大小分子补水锁水）",
        "天然蘑菇葡聚糖（增强皮肤免疫力）",
        "1,2-戊二醇 ≥5%（温和防腐替代传统防腐剂）",
        "鲨肝醇（促进红细胞生长、抗炎抗过敏）",
        "卵磷脂（保湿抗氧化）",
        "生育酚/维生素E（抗老养肤）",
    ],
    "claims_detected": [
        "修护皮肤屏障",
        "舒缓敏感泛红",
        "深层补水保湿",
        "临床验证有效",
        "法国贝桑松大学双盲对照实验证实",
        "痤疮辅助治疗有效率83.33%",
    ],
    "clinical_data": [
        "法国贝桑松大学Philippe Humbert教授团队双盲自身对照试验，论文发表于Journal of Cosmetic Dermatology 2018",
        "83名痤疮患者临床试验：实验组使用特护霜30天后皮损改善有效率83.33%，对照组48.78%",
        "54家国内著名三甲医院（含北大第一医院、中国医科大学附属医院等）多中心临床观察验证",
        "品牌团队产出128篇高质量学术论文，含Nature Communications等顶刊",
        "参与制定13份中国皮肤科临床专家共识及诊疗指南",
    ],
    "risk_or_uncertainty_points": [
        "各活性成分精确浓度未公开（属商业配方机密）",
        "含植物油脂和糖类保湿成分，大油皮可能闷痘",
        "北方冬季单用可能偏干，需搭配保湿霜",
    ],
    "suitable_skin_types_or_users": [
        "敏感肌（核心人群）",
        "干性肌肤",
        "混合偏干肌肤",
        "痘敏肌肤",
        "玫瑰痤疮伴敏感人群",
        "换季/环境变化/化妆品刺激导致的敏感问题",
        "医美术后修护（温和无刺激）",
        "孕妇哺乳期可用（无香精无防腐剂无激素）",
    ],
    "usage_scenarios": [
        "日常早晚护肤（洁面后涂抹）",
        "换季敏感急救",
        "医美术后修护打底",
        "晒后舒缓修护",
    ],
    "texture_and_feel": (
        "双皮奶般轻盈质地，触肤即化水感，涂抹过程舒适，"
        "吸收后无粘腻感，无香味。南方常年使用舒适，北方冬季可能需叠加保湿。"
    ),
    "target_audience": "敏感肌人群为主，覆盖18-45岁各肤质（尤其干敏、痘敏）",
    "competitive_position": (
        "国货功效护肤头部品牌，皮肤科背景，对标雅漾、理肤泉等药妆品牌。"
        "蝉联天猫双11舒敏面霜TOP1，两次登上世界皮肤大会。"
        "定价188元，低于雅漾（260+）和理肤泉（280+），高于普通国货面霜。"
    ),
    "questionnaire_focus": [
        "敏感肌修护可信度",
        "临床数据对购买决策的影响",
        "价格接受度",
        "质地体验预期",
        "与药妆竞品的对比",
    ],
    "description": (
        "薇诺娜舒敏保湿特护霜（第二代），含青刺果油、马齿苋精华、双分子透明质酸钠、"
        "天然蘑菇葡聚糖等核心成分，主打修护皮肤屏障+舒缓敏感+深层保湿三效合一。"
        "无香精无防腐剂无酒精无色素无激素，通过法国贝桑松大学双盲临床试验验证，"
        "54家三甲医院多中心临床观察，皮肤科医生推荐。双皮奶质地，轻盈不粘腻。"
        "天猫双11舒敏面霜TOP1，小红书50万+笔记，抖音月销10万+。"
        "适合敏感肌、干皮、痘敏肌、医美术后修护、孕妇哺乳期使用。188元/50g。"
    ),
    "confidence": 0.95,
}

# --- 稀疏产品 2: 珀莱雅双抗（中端·精华·稀疏） ---
PRODUCT_PROYA = {
    "id": "proya_sparse",
    "name": "珀莱雅双抗精华2.0",
    "brand": "珀莱雅（PROYA）",
    "category": "护肤",
    "sub_category": "精华",
    "price": 169,
    "price_range": "100-200",
    "target_channel": "ec",
    "main_selling_points": [
        "抗糖抗氧双重功效",
        "早C晚A搭配使用",
    ],
    "key_ingredients_or_features": ["虾青素", "麦角硫因"],
    "description": "珀莱雅双抗精华2.0，主打抗糖抗氧，含虾青素和麦角硫因。169元/30ml。",
    "confidence": 0.6,
}

# --- 详细产品 3: SK-II神仙水（高端·精华水·详细） ---
PRODUCT_SKII = {
    "id": "skii_detailed",
    "name": "SK-II护肤精华露（神仙水）",
    "brand": "SK-II",
    "category": "护肤",
    "sub_category": "精华水",
    "price": 590,
    "price_range": "500-1000",
    "target_channel": "ec",
    "main_selling_points": [
        "90%以上PITERA精华",
        "改善肤质五大维度：细滑度、紧致度、抗皱力、光泽度、白皙度",
        "日本匠心发酵工艺，源自清酒酿造启发",
        "全球畅销40年经典",
        "一瓶多效，简化护肤步骤",
    ],
    "key_ingredients_or_features": [
        "PITERA（半乳糖酵母样菌发酵产物滤液，富含50+微量营养素）",
        "天然保湿因子NMF",
        "有机酸",
        "矿物质",
        "氨基酸",
    ],
    "claims_detected": [
        "改善肌肤纹理",
        "提升肌肤透亮度",
        "调节肌肤水油平衡",
        "28天肌肤焕变",
        "连续使用肤质逐步改善",
    ],
    "clinical_data": [
        "品牌宣称28天肤质改善，但具体临床试验数据未公开",
        "基于品牌长期消费者反馈数据",
    ],
    "risk_or_uncertainty_points": [
        "PITERA具体浓度未公开",
        "590元/75ml价格门槛高",
        "部分用户反馈有轻微刺痛感（正常代谢反应）",
        "味道独特，部分消费者不适应（发酵气味）",
    ],
    "suitable_skin_types_or_users": [
        "所有肤质（油皮尤佳）",
        "关注肤质改善的25-45岁女性",
        "追求简单高效护肤流程的消费者",
        "有一定经济实力的护肤爱好者",
    ],
    "texture_and_feel": "透明水状质地，轻薄如水，拍打吸收快，无粘腻感。有独特发酵气味。",
    "target_audience": "25-45岁中高收入女性，追求肤质改善",
    "competitive_position": (
        "高端护肤标杆品牌，对标兰蔻、雅诗兰黛精华。"
        "天猫精华水品类常年TOP3。590元定价属于高端入门。"
    ),
    "description": (
        "SK-II护肤精华露（神仙水），含90%以上PITERA精华，"
        "改善肌肤细滑度、紧致度、抗皱力、光泽度、白皙度五大维度。"
        "日本发酵工艺，全球畅销40年。590元/75ml。"
    ),
    "confidence": 0.85,
}

# --- 稀疏产品 4: 韩束红蛮腰面霜（低端·面霜·稀疏） ---
PRODUCT_KANS = {
    "id": "kans_sparse",
    "name": "韩束红蛮腰紧致面霜",
    "brand": "韩束（KANS）",
    "category": "护肤",
    "sub_category": "面霜",
    "price": 79,
    "price_range": "50-100",
    "target_channel": "ec",
    "main_selling_points": [
        "红蛮腰抗皱系列",
        "紧致淡纹",
    ],
    "key_ingredients_or_features": ["红景天", "胶原蛋白肽"],
    "description": "韩束红蛮腰紧致面霜，主打紧致淡纹，含红景天和胶原蛋白肽。79元/50g。抖音直播间热销。",
    "confidence": 0.5,
}

# --- 稀疏产品 5: 欧莱雅男士控油洁面（低端·男士·稀疏） ---
PRODUCT_LOREAL_MEN = {
    "id": "loreal_men_sparse",
    "name": "欧莱雅男士火山岩控油洁面乳",
    "brand": "欧莱雅男士（L'Oreal Men Expert）",
    "category": "男士护理",
    "sub_category": "洁面",
    "price": 39,
    "price_range": "30-50",
    "target_channel": "ec",
    "main_selling_points": [
        "火山岩矿物控油",
        "深层清洁毛孔",
    ],
    "key_ingredients_or_features": ["火山岩矿物", "水杨酸"],
    "description": "欧莱雅男士火山岩控油洁面乳，深层清洁控油，含火山岩矿物和水杨酸。39元/100ml。京东男士洁面销量TOP。",
    "confidence": 0.55,
}

# 产品注册表
ALL_PRODUCTS = {
    "winona": PRODUCT_WINONA,
    "proya": PRODUCT_PROYA,
    "skii": PRODUCT_SKII,
    "kans": PRODUCT_KANS,
    "loreal_men": PRODUCT_LOREAL_MEN,
}

DETAILED_PRODUCTS = ["winona", "skii"]
SPARSE_PRODUCTS = ["proya", "kans", "loreal_men"]


# ============================================================================
# AI 调用
# ============================================================================

async def generate_survey(
    client, endpoint_id: str, product: dict, max_retries: int = 3,
) -> list[dict] | None:
    """Generate a full 30-question survey for a product, with retry."""
    rendered, _, _ = render_prompt(
        "survey_generate",
        product_ai_summary=product,
        user_role_type="manufacturer",
        extra_focus="",
    )
    for attempt in range(1, max_retries + 1):
        try:
            raw = await client.complete_json(
                system="你是一个专业的问卷设计师。严格按规则生成问卷，只输出JSON。",
                user=rendered,
                endpoint_id=endpoint_id,
            )
            data = parse_json_response(raw)
            if isinstance(data, dict):
                questions = data.get("questions", [])
                if questions:
                    return questions
            print(f"  [{product['name'][:6]}] survey attempt {attempt}: empty, retrying...")
        except Exception as e:
            print(f"  [{product['name'][:6]}] survey attempt {attempt} failed: {e}")
        if attempt < max_retries:
            await asyncio.sleep(2 * attempt)
    print(f"  [{product['name'][:6]}] survey: all {max_retries} attempts failed")
    return None


async def run_persona_answer(
    client, endpoint_id: str, persona: dict, product: dict,
    questions: list[dict], semaphore: asyncio.Semaphore,
    max_retries: int = 3,
) -> dict | None:
    """Run one persona answering a survey, with retry and global semaphore."""
    rendered, _, _ = render_prompt(
        "persona_answer",
        persona=persona,
        product_ai_summary=product,
        survey_questions=questions,
    )
    async with semaphore:
        for attempt in range(1, max_retries + 1):
            try:
                raw = await client.complete_json(
                    system="你是一个消费者模拟系统。严格按照角色设定回答问卷，只输出JSON。",
                    user=rendered,
                    endpoint_id=endpoint_id,
                )
                result = parse_json_response(raw)
                if result and result.get("answers"):
                    return result
                print(f"    [WARN] {persona['name']}: attempt {attempt} empty answers, retrying...")
            except Exception as e:
                print(f"    [ERROR] {persona['name']}: attempt {attempt} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2 * attempt)
    print(f"    [FAIL] {persona['name']}: all {max_retries} attempts failed")
    return None


# ============================================================================
# 输出
# ============================================================================

def print_survey(questions: list[dict], product_name: str = ""):
    print(f"\n{'='*80}")
    print(f"SURVEY ({product_name}): {len(questions)} questions")
    print(f"{'='*80}")
    for q in questions:
        qid = q.get("id", "?")
        dim = q.get("dim", "?")
        qtype = q.get("type", "?")
        text = q.get("question", "?")
        opts = q.get("options")
        print(f"\n  [{qid}] ({dim} / {qtype})")
        print(f"  {text}")
        if opts:
            for i, opt in enumerate(opts):
                print(f"    {chr(65+i)}. {opt}")


def print_persona_result(persona: dict, result: dict | None, questions: list[dict]):
    name = persona["name"]
    tag = persona.get("persona_tag", "")
    age = persona.get("age", "?")
    city = persona.get("city", "?")
    occ = persona.get("occupation", "?")
    income = persona.get("income_monthly", "?")

    print(f"\n{'#'*80}")
    print(f"# {name} | {tag}")
    print(f"# {age}岁 | {city} | {occ} | 月收入{income}")
    print(f"{'#'*80}")

    if not result:
        print("  [ERROR] No result")
        return

    print(f"\n  overall_intent: {result.get('overall_intent')}")
    print(f"  sentiment:      {result.get('sentiment')}")
    print(f"  verdict:        {result.get('one_sentence_verdict')}")

    thinking = result.get("thinking_process", "")
    if thinking:
        print(f"\n  === THINKING PROCESS ({len(thinking)}字) ===")
        for line in thinking.split("\n"):
            if line.strip():
                print(f"  {line}")

    summary = result.get("summary_comment", "")
    if summary:
        print(f"\n  === SUMMARY COMMENT ({len(summary)}字) ===")
        print(f"  {summary}")

    answers = result.get("answers", [])
    q_map = {q.get("id"): q for q in questions}

    print(f"\n  === ANSWERS ({len(answers)}/{len(questions)}) ===")
    for a in answers:
        qid = a.get("qid", "?")
        q = q_map.get(qid, {})
        dim = q.get("dim", "?")
        qtype = a.get("type", q.get("type", "?"))
        q_text = q.get("question", "")
        answer = a.get("answer", "?")
        reason = a.get("reason_short", "")

        print(f"\n  [{qid}] ({dim} / {qtype}) {q_text}")
        if isinstance(answer, list):
            print(f"    答: {', '.join(str(x) for x in answer)}")
        else:
            print(f"    答: {answer}")
        if reason:
            print(f"    因: {reason}")


def print_comparison(personas: list[dict], results: dict[str, dict | None], questions: list[dict]):
    print(f"\n\n{'='*80}")
    print("CROSS-PERSONA COMPARISON")
    print(f"{'='*80}")

    print("\n--- Overall Intent ---")
    print(f"{'name':<10} | {'score':>5} | {'sentiment':<10} | verdict")
    print("-" * 70)
    for p in personas:
        r = results.get(p["name"])
        if r:
            print(
                f"{p['name']:<10} | "
                f"{r.get('overall_intent', '?'):>5} | "
                f"{r.get('sentiment', '?'):<10} | "
                f"{r.get('one_sentence_verdict', '')}"
            )
        else:
            print(f"{p['name']:<10} | ERROR")

    answers_by_qid: dict[str, dict[str, dict]] = {}
    for p in personas:
        r = results.get(p["name"])
        if not r:
            continue
        for a in r.get("answers", []):
            qid = a.get("qid", "?")
            answers_by_qid.setdefault(qid, {})[p["name"]] = a

    for q in questions:
        qid = q.get("id")
        dim = q.get("dim")
        qtype = q.get("type")
        q_text = q.get("question", "")

        print(f"\n--- [{qid}] ({dim}/{qtype}) {q_text} ---")

        persona_answers = answers_by_qid.get(qid, {})
        for p in personas:
            a = persona_answers.get(p["name"])
            if not a:
                print(f"  {p['name']:<10}: [missing]")
                continue
            ans = a.get("answer", "?")
            reason = a.get("reason_short", "")
            if isinstance(ans, list):
                ans_str = ", ".join(str(x) for x in ans)
            else:
                ans_str = str(ans)
            print(f"  {p['name']:<10}: {ans_str}")
            if reason:
                print(f"  {'':>10}  -> {reason}")


def save_results(
    product: dict, questions: list[dict], results: dict[str, dict | None],
    suffix: str = "",
):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"persona_survey_{product.get('id', 'unknown')}{suffix}.json"
    out_path = OUTPUT_DIR / fname
    data = {
        "product": product,
        "questions": questions,
        "results": {name: result for name, result in results.items()},
    }
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nResults saved to: {out_path}")
    return out_path


def print_score_distribution(product_name: str, results: dict[str, dict | None]):
    """Print score distribution for one product."""
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    errors = 0
    for name, r in results.items():
        if not r or r.get("overall_intent") is None:
            errors += 1
            continue
        s = r["overall_intent"]
        dist[s] = dist.get(s, 0) + 1
    total = sum(dist.values())
    print(f"\n  {product_name}:")
    for k in sorted(dist):
        bar = "█" * dist[k]
        pct = f"{dist[k]/total*100:.0f}%" if total else "0%"
        print(f"    {k}★: {dist[k]:>2}人 ({pct:>4}) {bar}")
    if errors:
        print(f"    ERR: {errors}人")
    print(f"    Total: {total}人")


# ============================================================================
# 单产品运行
# ============================================================================

async def run_single_product(
    client, survey_endpoint: str, answer_endpoint: str,
    product: dict, personas: list[dict], semaphore: asyncio.Semaphore,
    verbose: bool = True,
) -> tuple[list[dict], dict[str, dict | None]]:
    """Run full survey + all persona answers for one product."""
    pname = product["name"][:10]
    print(f"\n{'='*80}")
    print(f"[{pname}] Generating survey...")
    print(f"{'='*80}")

    t0 = time.time()
    questions = await generate_survey(client, survey_endpoint, product)
    t1 = time.time()

    if not questions:
        print(f"[{pname}] FATAL: Survey generation failed")
        return [], {}

    print(f"[{pname}] Generated {len(questions)} questions in {t1-t0:.1f}s")

    if verbose:
        print_survey(questions, pname)

    # Persona answers
    results: dict[str, dict | None] = {}
    timings: dict[str, float] = {}

    async def _run_one(persona: dict) -> None:
        name = persona["name"]
        print(f"  [{pname}] Running {name}...", flush=True)
        t0 = time.time()
        result = await run_persona_answer(
            client, answer_endpoint, persona, product, questions, semaphore,
        )
        t1 = time.time()
        results[name] = result
        timings[name] = t1 - t0
        status = f"done ({t1-t0:.1f}s, {len(result.get('answers',[]))} ans)" if result else f"ERROR ({t1-t0:.1f}s)"
        print(f"  [{pname}] {name}: {status}")

    t_all_start = time.time()
    await asyncio.gather(*[_run_one(p) for p in personas])
    t_all_end = time.time()
    print(f"\n[{pname}] All {len(personas)} personas done in {t_all_end-t_all_start:.1f}s")

    if verbose:
        for persona in personas:
            print_persona_result(persona, results.get(persona["name"]), questions)
        print_comparison(personas, results, questions)

    return questions, results


# ============================================================================
# main
# ============================================================================

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Persona survey test")
    parser.add_argument(
        "--product",
        choices=["detailed", "sparse", "all", *ALL_PRODUCTS.keys()],
        default="detailed",
        help="Product to test: 'detailed' (winona), 'sparse' (proya), 'all' (5 products parallel), or a specific product key",
    )
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent API calls")
    parser.add_argument("--quiet", action="store_true", help="Only print summary, skip per-persona details")
    args, _ = parser.parse_known_args()

    personas = load_personas(start=1, end=32)
    client = get_ai_client()
    router = ModelRouter()
    survey_route = router.get(TaskType.SURVEY_GENERATE)
    answer_route = router.get(TaskType.PERSONA_ANSWER)

    # Global semaphore shared across all products
    semaphore = asyncio.Semaphore(args.concurrency)
    verbose = not args.quiet

    print(f"AI Provider: {os.environ.get('AI_PROVIDER')}")
    print(f"Survey endpoint: {survey_route.endpoint_id}")
    print(f"Answer endpoint: {answer_route.endpoint_id}")
    print(f"Concurrency: {args.concurrency}")
    print(f"Personas: {len(personas)} ({[p['name'] for p in personas]})")

    # Resolve product list
    if args.product == "detailed":
        product_keys = ["winona"]
    elif args.product == "sparse":
        product_keys = ["proya"]
    elif args.product == "all":
        product_keys = list(ALL_PRODUCTS.keys())
    else:
        product_keys = [args.product]

    products = [ALL_PRODUCTS[k] for k in product_keys]
    print(f"Products ({len(products)}): {[p['name'] for p in products]}")

    # Run products sequentially, personas in parallel within each product
    t_global_start = time.time()
    all_results = []

    for i, product in enumerate(products, 1):
        print(f"\n\n{'*'*80}")
        print(f"PRODUCT {i}/{len(products)}: {product['name']} (¥{product['price']})")
        print(f"{'*'*80}")
        questions, results = await run_single_product(
            client, survey_route.endpoint_id, answer_route.endpoint_id,
            product, personas, semaphore, verbose=verbose,
        )
        if questions and results:
            save_results(product, questions, results)
        all_results.append((product, questions, results))
    t_global_end = time.time()

    # Final summary
    print(f"\n\n{'='*80}")
    print(f"FINAL SUMMARY — {len(products)} products x {len(personas)} personas")
    print(f"Total wall time: {t_global_end-t_global_start:.1f}s")
    print(f"{'='*80}")

    for product, questions, results in all_results:
        if results:
            print_score_distribution(product["name"], results)

    # Cross-product comparison matrix
    if len(products) > 1:
        print(f"\n{'='*80}")
        print("CROSS-PRODUCT SCORE MATRIX")
        print(f"{'='*80}")
        # Header
        p_names_short = [p["name"][:8] for p, _, _ in all_results]
        header = f"{'角色':<10}" + "".join(f" | {n:>8}" for n in p_names_short)
        print(header)
        print("-" * len(header))
        for persona in personas:
            row = f"{persona['name']:<10}"
            for product, questions, results in all_results:
                r = results.get(persona["name"]) if results else None
                score = r.get("overall_intent", "?") if r else "ERR"
                row += f" | {score:>8}"
            print(row)

    # Also save a combined results file for multi-product runs
    if len(products) > 1:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        combined = {}
        for product, questions, results in all_results:
            pid = product.get("id", product["name"])
            combined[pid] = {
                "product": product,
                "questions": questions,
                "results": results,
            }
        combined_path = OUTPUT_DIR / "persona_survey_all_products.json"
        combined_path.write_text(
            json.dumps(combined, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nCombined results saved to: {combined_path}")

    print(f"\n{'='*80}")
    print("DONE")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
