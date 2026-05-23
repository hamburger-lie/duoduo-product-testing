"""Complete persona survey test — real AI, full 30-question survey.

Step 1: Generate a full 30-question survey for a test product.
Step 2: Each of the 5 personas answers the full survey.
Step 3: Print every persona's complete output (thinking, verdict, summary, all 30 answers).
Step 4: Print cross-persona comparison.

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/persona_full_survey_test.py
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


def load_personas(start: int = 1, end: int = 15) -> list[dict]:
    personas = []
    for f in sorted(PERSONAS_DIR.glob("persona_beauty_*.json")):
        num = int(f.stem.split("_")[-1])
        if start <= num <= end:
            with open(f, encoding="utf-8") as fh:
                personas.append(json.load(fh))
    return personas


TEST_PRODUCT = {
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


async def generate_survey(client, endpoint_id: str) -> list[dict] | None:
    """Generate a full 30-question survey."""
    rendered, _, _ = render_prompt(
        "survey_generate",
        product_ai_summary=TEST_PRODUCT,
        user_role_type="manufacturer",
        extra_focus="",
    )
    try:
        raw = await client.complete_json(
            system="你是一个专业的问卷设计师。严格按规则生成问卷，只输出JSON。",
            user=rendered,
            endpoint_id=endpoint_id,
        )
        data = parse_json_response(raw)
        if isinstance(data, dict):
            return data.get("questions", [])
        return None
    except Exception as e:
        print(f"[ERROR] Survey generation failed: {e}")
        return None


async def run_persona_answer(
    client, endpoint_id: str, persona: dict, questions: list[dict]
) -> dict | None:
    """Run one persona answering the full survey."""
    rendered, _, _ = render_prompt(
        "persona_answer",
        persona=persona,
        product_ai_summary=TEST_PRODUCT,
        survey_questions=questions,
    )
    try:
        raw = await client.complete_json(
            system="你是一个消费者模拟系统。严格按照角色设定回答问卷，只输出JSON。",
            user=rendered,
            endpoint_id=endpoint_id,
        )
        return parse_json_response(raw)
    except Exception as e:
        print(f"    [ERROR] {persona['name']}: {e}")
        return None


def print_survey(questions: list[dict]):
    """Print the full survey."""
    print(f"\n{'='*80}")
    print(f"SURVEY: {len(questions)} questions")
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
    """Print one persona's complete answer."""
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
    """Print cross-persona comparison for key questions."""
    print(f"\n\n{'='*80}")
    print("CROSS-PERSONA COMPARISON")
    print(f"{'='*80}")

    # Overall scores
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

    # Collect all answers by qid
    answers_by_qid: dict[str, dict[str, dict]] = {}
    for p in personas:
        r = results.get(p["name"])
        if not r:
            continue
        for a in r.get("answers", []):
            qid = a.get("qid", "?")
            answers_by_qid.setdefault(qid, {})[p["name"]] = a

    # Print comparison for each question
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


def save_results(questions: list[dict], results: dict[str, dict | None]):
    """Save full results to JSON for later analysis."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "persona_full_survey_results.json"
    data = {
        "product": TEST_PRODUCT,
        "questions": questions,
        "results": {
            name: result for name, result in results.items()
        },
    }
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nResults saved to: {out_path}")


async def main():
    # Test all 15 personas
    personas = load_personas(start=1, end=15)
    client = get_ai_client()
    router = ModelRouter()

    survey_route = router.get(TaskType.SURVEY_GENERATE)
    answer_route = router.get(TaskType.PERSONA_ANSWER)

    print(f"AI Provider: {os.environ.get('AI_PROVIDER')}")
    print(f"Survey endpoint: {survey_route.endpoint_id}")
    print(f"Answer endpoint: {answer_route.endpoint_id}")
    print(f"Product: {TEST_PRODUCT['name']} (RMB{TEST_PRODUCT['price']})")
    print(f"Personas: {[p['name'] for p in personas]}")

    # Step 1: Generate survey
    print(f"\n{'='*80}")
    print("STEP 1: Generating 30-question survey...")
    print(f"{'='*80}")
    t0 = time.time()
    questions = await generate_survey(client, survey_route.endpoint_id)
    t1 = time.time()

    if not questions:
        print("FATAL: Survey generation failed")
        return

    print(f"Generated {len(questions)} questions in {t1-t0:.1f}s")
    print_survey(questions)

    if len(questions) != 30:
        print(f"WARNING: Expected 30 questions, got {len(questions)}")

    # Step 2: Each persona answers (concurrent, Semaphore=3, like production)
    _CONCURRENCY = 3
    print(f"\n\n{'='*80}")
    print(f"STEP 2: Persona answers (10 personas x 30 questions, Semaphore={_CONCURRENCY})")
    print(f"{'='*80}")

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    results: dict[str, dict | None] = {}
    timings: dict[str, float] = {}

    async def _run_one(persona: dict) -> None:
        name = persona["name"]
        async with semaphore:
            print(f"\n  Running {name}...", end=" ", flush=True)
            t0 = time.time()
            result = await run_persona_answer(
                client, answer_route.endpoint_id, persona, questions,
            )
            t1 = time.time()
            results[name] = result
            timings[name] = t1 - t0
            if result:
                n_answers = len(result.get("answers", []))
                print(f"done ({t1-t0:.1f}s, {n_answers} answers)")
            else:
                print(f"ERROR ({t1-t0:.1f}s)")

    t_all_start = time.time()
    await asyncio.gather(*[_run_one(p) for p in personas])
    t_all_end = time.time()
    print(f"\n  All personas done in {t_all_end-t_all_start:.1f}s (wall clock)")
    for name, t in timings.items():
        print(f"    {name}: {t:.1f}s")

    # Step 3: Print full results per persona
    print(f"\n\n{'='*80}")
    print("STEP 3: FULL RESULTS PER PERSONA")
    print(f"{'='*80}")

    for persona in personas:
        print_persona_result(persona, results.get(persona["name"]), questions)

    # Step 4: Cross-persona comparison
    print_comparison(personas, results, questions)

    # Save
    save_results(questions, results)

    print(f"\n{'='*80}")
    print("DONE")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
