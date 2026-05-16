from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent
SOURCE_DIR = PROJECT_ROOT / "docs" / "SEEDS" / "personas"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "SEEDS" / "personas_v2"

# ── 新字段列表 ──────────────────────────────────────────────────────────────
# 如果 seed 里已经手写了这些字段，引擎直接使用；
# 缺失时才执行下面的 fallback 推断函数。
_V2_FIELDS = [
    "mind_model",
    "decision_heuristics",
    "expression_dna",
    "anti_patterns",
    "scoring_bias",
    "honest_boundaries",
    "attention_bias",
    "ignored_signals",
    "price_anchors",
    "impulse_triggers",
    "dealbreakers",
    "tradeoff_rules",
]


def load_json(path: Path) -> dict[str, Any]:
    """Load one persona seed JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write one persona seed JSON file."""
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ── Fallback 推断函数（仅在手写字段缺失时调用）────────────────────────────

def _fallback_mind_model(seed: dict[str, Any]) -> list[str]:
    """Fallback: infer a basic mind model when not hand-written."""
    profile = seed.get("profile", {})
    tag = str(seed.get("persona_tag", ""))
    price_sensitivity = str(profile.get("price_sensitivity", ""))
    concerns = "、".join(profile.get("skincare_concerns", []))

    rules = [
        "护肤品不是越贵越好，核心是成分、肤感、适用肤质和长期稳定性。",
        "品牌故事可以加分，但不能替代真实功效证据和用户评价。",
    ]
    if "成分" in tag or "成分" in str(profile.get("decision_style", "")):
        rules.append("如果一个产品不讲清楚关键成分和适用人群，可信度会下降。")
    elif "性价比" in tag or "高" in price_sensitivity:
        rules.append("只要价格明显高于同类产品，就必须有更强的效果、容量或口碑支撑。")
    elif "敏感" in concerns or "屏障" in concerns:
        rules.append("温和和稳定比短期猛效果更重要，刺激风险会直接影响购买意愿。")
    else:
        rules.append("爆款声量只能带来兴趣，最后还是要看真实评价和自己使用场景。")
    return rules


def _fallback_decision_heuristics(seed: dict[str, Any]) -> list[dict[str, str]]:
    """Fallback: infer basic buy/reject heuristics."""
    profile = seed.get("profile", {})
    tag = str(seed.get("persona_tag", ""))
    heuristics = [
        {
            "trigger": "看到明确成分、适用肤质和使用场景",
            "effect": "提高信任和购买意愿",
        },
        {
            "trigger": "功效描述很夸张但没有证据",
            "effect": "降低评分，认为是营销话术",
        },
    ]
    if seed.get("is_critical") or "成分" in tag:
        heuristics.append(
            {
                "trigger": "关键成分浓度、功效路径或竞品对比不清楚",
                "effect": "先观望，不会直接下单",
            }
        )
    elif "price_sensitivity" in profile:
        heuristics.append(
            {
                "trigger": "价格高于自己的日常护肤预算",
                "effect": "会等待大促或寻找替代品",
            }
        )
    else:
        heuristics.append(
            {
                "trigger": "身边人或常看平台出现真实好评",
                "effect": "愿意加入购物车或先买小规格试试",
            }
        )
    return heuristics


def _fallback_expression_dna(seed: dict[str, Any]) -> dict[str, Any]:
    """Fallback: infer expression style."""
    profile = seed.get("profile", {})
    tag = str(seed.get("persona_tag", ""))
    if seed.get("is_critical") or "成分" in tag:
        tone = "理性、克制、略挑剔"
        sentence_style = "短句多，会先肯定一点再指出顾虑"
        keywords = ["成分", "浓度", "肤感", "刺激感", "性价比", "证据"]
    elif "性价比" in tag:
        tone = "直接、务实、会算账"
        sentence_style = "常把价格和替代品放在一起比较"
        keywords = ["划算", "预算", "大促", "平替", "值不值"]
    else:
        tone = "自然、具体、带生活感"
        sentence_style = "会结合自己的日常场景表达感受"
        keywords = ["方便", "舒服", "评价", "适合我", "会不会踩雷"]
    return {
        "tone": tone,
        "sentence_style": sentence_style,
        "keywords": keywords,
        "pet_phrases": profile.get("pet_phrases", []),
    }


def _fallback_anti_patterns(seed: dict[str, Any]) -> list[str]:
    """Fallback: infer what this persona rejects."""
    profile = seed.get("profile", {})
    anti_patterns = [
        "反感夸张功效",
        "反感没有依据的敏感肌可用",
        "反感全网爆款但真实评价很空",
    ]
    for pain in profile.get("pain_points", []):
        if pain not in anti_patterns:
            anti_patterns.append(str(pain))
    return anti_patterns[:5]


def _fallback_scoring_bias(seed: dict[str, Any]) -> dict[str, Any]:
    """Fallback: infer score tendency."""
    if seed.get("is_critical"):
        return {
            "default_score": 3,
            "volatility": "low",
            "score_5_trigger": "成分明确、证据充分、价格和竞品相比说得通",
            "score_4_trigger": "卖点清晰、价格合理、无明显短板",
            "score_2_trigger": "功效夸张、证据不足、价格虚高",
            "score_1_trigger": "严重虚假宣传或对该角色完全无用",
        }
    return {
        "default_score": 4,
        "volatility": "medium",
        "score_5_trigger": "卖点清晰、价格可接受、适合自己的生活场景、口碑好",
        "score_4_trigger": "整体不错，无明显短板",
        "score_2_trigger": "信息含糊、真实评价少、价格或使用门槛过高",
        "score_1_trigger": "完全不适合该角色的需求或肤质",
    }


def _fallback_attention_bias(seed: dict[str, Any]) -> list[str]:
    """Fallback: infer what this persona notices first."""
    tag = str(seed.get("persona_tag", ""))
    if "成分" in tag:
        return ["第一眼：成分表", "第二眼：浓度", "第三眼：价格与竞品对比"]
    if "性价比" in tag:
        return ["第一眼：价格和到手价", "第二眼：赠品和套装", "第三眼：是否适合自己"]
    return ["第一眼：整体观感", "第二眼：价格", "第三眼：是否适合自己"]


def _fallback_ignored_signals(seed: dict[str, Any]) -> list[str]:
    """Fallback: infer what this persona ignores."""
    return ["品牌历史故事", "过于专业的成分学术分析", "爆款排行榜"]


def _fallback_price_anchors(seed: dict[str, Any]) -> dict[str, Any]:
    """Fallback: infer price psychology."""
    income = seed.get("income_monthly", 10000)
    if income < 5000:
        return {
            "too_cheap": 20,
            "comfortable": 80,
            "too_expensive": 200,
            "anchor_reference": "平价国货",
        }
    if income < 12000:
        return {
            "too_cheap": 30,
            "comfortable": 150,
            "too_expensive": 300,
            "anchor_reference": "国货中端",
        }
    return {
        "too_cheap": 50,
        "comfortable": 300,
        "too_expensive": 800,
        "anchor_reference": "国际大牌",
    }


def _fallback_impulse_triggers(seed: dict[str, Any]) -> list[str]:
    """Fallback: infer impulse buying triggers."""
    tag = str(seed.get("persona_tag", ""))
    if "性价比" in tag or "直播" in str(seed.get("profile", {}).get("info_channels", [])):
        return ["直播间限时优惠+赠品多", "大促叠券价格很低"]
    if "小红书" in str(seed.get("profile", {}).get("info_channels", [])):
        return ["小红书大量真人好评", "身边人推荐"]
    return ["口碑积累到一定程度", "遇到合适的优惠"]


def _fallback_dealbreakers(seed: dict[str, Any]) -> list[str]:
    """Fallback: infer deal-breaking conditions."""
    profile = seed.get("profile", {})
    base = ["严重的真实差评", "价格远超预算"]
    for _concern in profile.get("skincare_concerns", [])[:1]:
        base.append(f"产品不适合{profile.get('skin_type', '自己的肤质')}")
    return base


def _fallback_tradeoff_rules(seed: dict[str, Any]) -> list[dict[str, str]]:
    """Fallback: infer conflict resolution rules."""
    return [
        {"conflict": "价格高 vs 成分好", "choice": "根据预算决定，超预算就找平替"},
        {"conflict": "口碑好 vs 自己肤质不适合", "choice": "优先考虑自己的肤质"},
    ]


def _fallback_honest_boundaries() -> list[str]:
    return [
        "不知道产品没提供的真实检测数据",
        "不能假装已经长期使用过产品",
        "只能基于当前产品信息和个人偏好做模拟判断",
    ]


# ── 主构建函数 ───────────────────────────────────────────────────────────────

_FALLBACK_MAP: dict[str, Any] = {
    "mind_model": _fallback_mind_model,
    "decision_heuristics": _fallback_decision_heuristics,
    "expression_dna": _fallback_expression_dna,
    "anti_patterns": _fallback_anti_patterns,
    "scoring_bias": _fallback_scoring_bias,
    "attention_bias": _fallback_attention_bias,
    "ignored_signals": _fallback_ignored_signals,
    "price_anchors": _fallback_price_anchors,
    "impulse_triggers": _fallback_impulse_triggers,
    "dealbreakers": _fallback_dealbreakers,
    "tradeoff_rules": _fallback_tradeoff_rules,
}


def build_v2_persona(seed: dict[str, Any]) -> dict[str, Any]:
    """Build one Persona v2 seed.

    Strategy:
    - If the seed already has a v2 field hand-written → use it directly.
    - Otherwise → run the fallback inference function.

    This means hand-crafted seeds are never overwritten by the engine,
    while legacy v1 seeds get reasonable inferred values.
    """
    profile = dict(seed.get("profile", {}))

    # Ensure basic v1 fields exist
    profile.setdefault("bio", "")
    profile.setdefault("lifestyle", "")
    profile.setdefault("shopping_habits", "")
    profile.setdefault("decision_style", "")
    profile.setdefault("skincare_concerns", [])
    profile.setdefault("info_channels", [])

    # Fill v2 fields: hand-written takes priority, fallback only if missing
    for field in _V2_FIELDS:
        if field not in profile:
            fallback_fn = _FALLBACK_MAP.get(field)
            if fallback_fn is not None:
                if field == "honest_boundaries":
                    profile[field] = _fallback_honest_boundaries()
                else:
                    profile[field] = fallback_fn(seed)

    result = dict(seed)
    result["profile"] = profile
    return result


def validate_v2_persona(persona: dict[str, Any]) -> list[str]:
    """Return a list of validation warnings for a v2 persona.

    Does not raise — just reports issues so the caller can decide.
    """
    warnings: list[str] = []
    profile = persona.get("profile", {})
    name = persona.get("name", "?")

    scoring = profile.get("scoring_bias", {})
    if not scoring.get("score_5_trigger"):
        warnings.append(f"{name}: scoring_bias missing score_5_trigger")
    if not scoring.get("score_1_trigger"):
        warnings.append(f"{name}: scoring_bias missing score_1_trigger")

    mind = profile.get("mind_model", [])
    if len(mind) < 2:
        warnings.append(f"{name}: mind_model has fewer than 2 entries")

    heuristics = profile.get("decision_heuristics", [])
    if len(heuristics) < 3:
        warnings.append(f"{name}: decision_heuristics has fewer than 3 entries")

    if not profile.get("dealbreakers"):
        warnings.append(f"{name}: dealbreakers is empty")

    if not profile.get("impulse_triggers"):
        warnings.append(f"{name}: impulse_triggers is empty")

    return warnings


def build_all(source_dir: Path = SOURCE_DIR, output_dir: Path = OUTPUT_DIR) -> int:
    """Build Persona v2 seeds for every legacy persona seed.

    If output_dir already has v2 files with hand-written fields, those
    are used as the source (not source_dir). This allows iterative editing
    of v2 files without losing hand-written customisations.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    all_warnings: list[str] = []

    for path in sorted(source_dir.glob("*.json")):
        # Check if a v2 version already exists in output_dir
        v2_path = output_dir / path.name
        if v2_path.exists():
            seed = load_json(v2_path)  # prefer existing v2 (may have hand-written fields)
        else:
            seed = load_json(path)

        v2 = build_v2_persona(seed)
        warnings = validate_v2_persona(v2)
        all_warnings.extend(warnings)
        write_json(v2_path, v2)
        count += 1

    if all_warnings:
        for w in all_warnings:
            print(f"WARN: {w}")

    return count


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Build Persona v2 seed JSON files.")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    count = build_all(source_dir=args.source_dir, output_dir=args.output_dir)
    print(f"PERSONA_V2_BUILD_OK count={count} output={args.output_dir}")


if __name__ == "__main__":
    main()
