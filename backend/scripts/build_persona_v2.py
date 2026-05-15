from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent
SOURCE_DIR = PROJECT_ROOT / "docs" / "SEEDS" / "personas"
OUTPUT_DIR = PROJECT_ROOT / "docs" / "SEEDS" / "personas_v2"


def load_json(path: Path) -> dict[str, Any]:
    """Load one persona seed JSON file."""

    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write one persona seed JSON file."""

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def infer_mind_model(seed: dict[str, Any]) -> list[str]:
    """Infer a stable consumer mind model from legacy persona fields."""

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


def infer_decision_heuristics(seed: dict[str, Any]) -> list[dict[str, str]]:
    """Infer buy/reject heuristics from legacy persona fields."""

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


def infer_expression_dna(seed: dict[str, Any]) -> dict[str, Any]:
    """Infer expression style from persona tag and legacy pet phrases."""

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


def infer_anti_patterns(seed: dict[str, Any]) -> list[str]:
    """Infer what this persona rejects."""

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


def infer_scoring_bias(seed: dict[str, Any]) -> dict[str, Any]:
    """Infer score tendency."""

    if seed.get("is_critical"):
        default_score = 3
        high = "成分明确、证据充分、价格和竞品相比说得通"
        low = "功效夸张、证据不足、价格虚高或刺激风险不清楚"
    else:
        default_score = 4
        high = "卖点清晰、价格可接受、适合自己的生活场景"
        low = "信息含糊、真实评价少、价格或使用门槛过高"
    return {
        "default_score": default_score,
        "high_score_condition": high,
        "low_score_condition": low,
    }


def build_v2_persona(seed: dict[str, Any]) -> dict[str, Any]:
    """Build one Persona v2 seed from a legacy seed."""

    profile = dict(seed.get("profile", {}))
    profile.setdefault("bio", "")
    profile.setdefault("lifestyle", "")
    profile.setdefault("shopping_habits", "")
    profile.setdefault("decision_style", "")
    profile.setdefault("skincare_concerns", [])
    profile.setdefault("info_channels", [])
    profile["mind_model"] = infer_mind_model(seed)
    profile["decision_heuristics"] = infer_decision_heuristics(seed)
    profile["expression_dna"] = infer_expression_dna(seed)
    profile["anti_patterns"] = infer_anti_patterns(seed)
    profile["scoring_bias"] = infer_scoring_bias(seed)
    profile["honest_boundaries"] = [
        "不知道产品没提供的真实检测数据",
        "不能假装已经长期使用过产品",
        "只能基于当前产品信息和个人偏好做模拟判断",
    ]

    result = dict(seed)
    result["profile"] = profile
    return result


def build_all(source_dir: Path = SOURCE_DIR, output_dir: Path = OUTPUT_DIR) -> int:
    """Build Persona v2 seeds for every legacy persona seed."""

    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(source_dir.glob("*.json")):
        seed = load_json(path)
        output_path = output_dir / path.name
        write_json(output_path, build_v2_persona(seed))
        count += 1
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
