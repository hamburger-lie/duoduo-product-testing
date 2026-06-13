"""Quantitative quality comparison: thinking vs no-thinking survey output.

Scores a survey JSON (list of 30 questions) on objective metrics so we can
judge whether disabling DeepSeek reasoning degrades survey quality.

Usage:
    python scripts/survey_quality_diff.py <label> <questions.json> [...]
"""
from __future__ import annotations

import json
import sys
from collections import Counter

# Product-specific anchors for the 珀莱雅双抗精华2.0 test product
ANCHORS = {
    "成分": ["虾青素", "麦角硫因", "肌肽"],
    "卖点": ["双抗", "抗糖", "抗氧", "提亮"],
    "价格": ["169", "30ml"],
    "竞品": ["薇诺娜", "修丽可", "olay", "小白瓶", "竞品", "平替"],
    "渠道": ["抖音", "小红书", "直播", "种草", "博主"],
}

EXPECTED_DIMS = [
    "first_impression", "purchase_motivation", "price_sensitivity",
    "package_appearance", "competitor_comparison", "usage_scenario",
    "repurchase_intent", "nps_recommendation", "channel_touchpoint",
    "painpoint_improvement",
]
# Question-type contract (from prompt 结构规则 #4)
TYPE_TARGETS = {"single": (8, 10), "multi": (4, 6), "scale_1_5": (0, 4), "open": (12, 14)}


def score(label: str, questions: list[dict]) -> None:
    n = len(questions)
    texts = [q.get("question", "") for q in questions]
    blob = "\n".join(texts)

    # 1. Anchor coverage: how many questions touch each product anchor
    anchor_hits = {}
    for cat, words in ANCHORS.items():
        hits = sum(1 for t in texts if any(w.lower() in t.lower() for w in words))
        anchor_hits[cat] = hits
    total_anchored = sum(
        1 for t in texts
        if any(w.lower() in t.lower() for ws in ANCHORS.values() for w in ws)
    )

    # 2. Type distribution vs contract
    types = Counter(q.get("type", "?") for q in questions)

    # 3. Sentence-opener repetition (templating proxy): first 4 chars
    openers = Counter(t[:4] for t in texts if t)
    repeated = {k: v for k, v in openers.items() if v >= 3}

    # 4. Dimension coverage
    dims = Counter(q.get("dim", "?") for q in questions)
    dim_ok = all(dims.get(d, 0) == 3 for d in EXPECTED_DIMS)

    # 5. Avg question length (over-short = generic, over-long = breaks 40-char rule)
    avg_len = sum(len(t) for t in texts) / max(n, 1)
    over_40 = sum(1 for t in texts if len(t) > 40)

    print(f"\n{'='*60}\n{label}  (n={n})\n{'='*60}")
    print(f"锚点命中题数(去重): {total_anchored}/30  明细: {anchor_hits}")
    print(f"题型分布: {dict(types)}")
    for t, (lo, hi) in TYPE_TARGETS.items():
        got = types.get(t, 0)
        flag = "OK" if lo <= got <= hi else "!!"
        print(f"   {t:10s} {got:2d}  目标[{lo}-{hi}] {flag}")
    print(f"维度完整(每维度3题): {dim_ok}")
    print(f"开头重复(>=3次): {repeated or '无'}")
    print(f"平均题长: {avg_len:.1f}字  超40字: {over_40}题")


def main() -> None:
    args = sys.argv[1:]
    for i in range(0, len(args), 2):
        label, path = args[i], args[i + 1]
        data = json.load(open(path, encoding="utf-8"))
        questions = data["questions"] if isinstance(data, dict) else data
        score(label, questions)


if __name__ == "__main__":
    main()
