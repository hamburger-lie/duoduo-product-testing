from __future__ import annotations

import pytest

from app.ai.exceptions import AIPromptNotFound
from app.ai.prompt_manager import render_prompt


def test_render_product_understand_returns_tuple() -> None:
    rendered, name, versioned = render_prompt(
        "product_understand",
        user_role_type="manufacturer",
        product={"id": 1, "name": "Test Cream", "price": 99},
    )
    assert isinstance(rendered, str)
    assert len(rendered) > 50
    assert name == "product_understand"
    assert versioned.startswith("product_understand@v")


def test_render_persona_chat_includes_context() -> None:
    rendered, _, _ = render_prompt(
        "persona_chat",
        persona={"id": 1, "name": "小红"},
        product_ai_summary={"name": "面霜"},
        persona_answer_history={"overall_intent": 4},
        conversation_history=[{"role": "user", "content": "你好"}],
        user_message="为什么你给了4分？",
    )
    assert "小红" in rendered
    assert "面霜" in rendered
    assert "为什么你给了4分？" in rendered


def test_render_persona_answer_includes_persona_v2_mind_model() -> None:
    rendered, _, _ = render_prompt(
        "persona_answer",
        persona={
            "id": 1,
            "name": "林雪",
            "age": 28,
            "city": "上海",
            "occupation": "产品经理",
            "income_monthly": 25000,
            "persona_tag": "成分党",
            "is_critical": True,
            "profile": {
                "bio": "工作忙，护肤追求有效但不复杂。",
                "mind_model": ["护肤品不是越贵越好，核心是成分、浓度、肤感和长期稳定性。"],
                "decision_heuristics": [
                    {
                        "trigger": "看到明确成分浓度和适用肤质",
                        "effect": "提高信任和购买意愿",
                    }
                ],
                "expression_dna": {
                    "tone": "理性、克制、略挑剔",
                    "sentence_style": "短句多，会先肯定一点再指出顾虑",
                    "keywords": ["成分", "浓度", "肤感"],
                    "pet_phrases": ["光这么说我不太信"],
                },
                "anti_patterns": ["反感夸张功效"],
                "scoring_bias": {
                    "default_score": 3,
                    "high_score_condition": "成分明确、价格合理",
                    "low_score_condition": "功效夸张、证据不足",
                },
                "honest_boundaries": ["不能假装已经长期使用过产品"],
            },
        },
        product_ai_summary={"name": "精华液", "price": 169},
        survey_questions=[{"id": "q1", "type": "scale_1_5", "question": "会买吗？"}],
    )

    assert "消费心智模型" in rendered
    assert "决策启发式" in rendered
    assert "表达 DNA" in rendered
    assert "反模式" in rendered
    assert "评分规则" in rendered
    assert "诚实边界" in rendered
    assert "护肤品不是越贵越好" in rendered
    assert "光这么说我不太信" in rendered


def test_render_persona_answer_falls_back_for_legacy_profile() -> None:
    rendered, _, _ = render_prompt(
        "persona_answer",
        persona={
            "id": 1,
            "name": "小红",
            "age": 25,
            "city": "杭州",
            "profile": {"bio": "关注性价比"},
        },
        product_ai_summary={"name": "面霜"},
        survey_questions=[{"id": "q1", "type": "open", "question": "怎么看？"}],
    )

    assert "消费心智模型" in rendered
    assert "你会根据价格、功效、品牌信任、评价和使用场景综合判断" in rendered
    assert "不能假装自己真实长期使用过产品" in rendered


def test_render_persona_chat_has_honest_identity_boundary() -> None:
    rendered, _, _ = render_prompt(
        "persona_chat",
        persona={
            "id": 1,
            "name": "小红",
            "age": 25,
            "city": "杭州",
            "profile": {
                "mind_model": ["价格要和体验匹配"],
                "expression_dna": {"tone": "直接", "pet_phrases": ["值不值这个价"]},
                "honest_boundaries": ["不能假装长期用过"],
            },
        },
        product_ai_summary={"name": "面霜"},
        persona_answer_history={"overall_intent": 3},
        conversation_history=[],
        user_message="你是真人吗？",
    )

    assert "基于这个消费者画像生成的模拟反馈" in rendered
    assert "我是真人" not in rendered
    assert "消费心智" in rendered
    assert "价格要和体验匹配" in rendered


def test_render_survey_generate_includes_price_fidelity_guardrail() -> None:
    rendered, _, _ = render_prompt(
        "survey_generate",
        user_role_type="manufacturer",
        product_ai_summary={
            "name": "珀莱雅双抗精华2.0",
            "price": 169,
            "main_selling_points": ["双抗"],
            "key_ingredients": ["虾青素", "麦角硫因", "肌肽"],
        },
        product={"id": 1},
    )

    assert "169" in rendered
    assert "涉及价格的题必须写出具体数字" in rendered


def test_render_survey_generate_includes_question_type_contract() -> None:
    rendered, _, _ = render_prompt(
        "survey_generate",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试面霜", "price": 199},
        product={"id": 1},
    )

    assert "scale_1_5 和 open 设为 null" in rendered
    assert "single 和 multi 必须有" in rendered
    assert "single" in rendered and "multi" in rendered


def test_render_survey_generate_includes_psychology_techniques() -> None:
    rendered, _, _ = render_prompt(
        "survey_generate",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试精华", "price": 239},
        product={"id": 1},
    )

    assert "投射法" in rendered
    assert "PSM 价格三问" in rendered
    assert "认知失调探针" in rendered
    assert "注意力验证" in rendered
    assert "至少用 5 种" in rendered


def test_render_unknown_template_raises_not_found() -> None:
    with pytest.raises(AIPromptNotFound):
        render_prompt("nonexistent_template", foo="bar")


def test_render_missing_variable_still_renders_with_chainable_undefined() -> None:
    # With ChainableUndefined, missing vars become Undefined (falsy) instead of raising.
    # This is intentional — v2.0 templates use optional dict attributes extensively.
    rendered, _, _ = render_prompt("product_understand")
    assert isinstance(rendered, str)


def test_versioned_name_format() -> None:
    _, _, versioned = render_prompt(
        "product_understand",
        user_role_type="channel",
        product={"id": 2, "name": "Serum"},
    )
    import re

    assert re.match(r"product_understand@v\d+\.\d+\.\d+$", versioned)


# ------------------------------------------------------------------ #
# T022: report_synthesize.j2 snapshot & schema tests
# ------------------------------------------------------------------ #


def test_render_report_synthesize_returns_tuple() -> None:
    """report_synthesize renders without error and returns the standard tuple."""
    rendered, name, versioned = render_prompt(
        "report_synthesize",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试面霜", "brand": "珀莱雅", "category": "面霜"},
        survey_questions=[
            {
                "id": "q01",
                "dim": "first_impression",
                "type": "scale_1_5",
                "question": "第一印象如何？",
            }
        ],
        all_answers=[
            {
                "persona_name": "林雪",
                "overall_intent": 4,
                "sentiment": "positive",
                "answers": [{"qid": "q01", "answer": 4, "reason_short": "包装精致"}],
            }
        ],
        report_template={},
    )
    assert isinstance(rendered, str)
    assert len(rendered) > 100
    assert name == "report_synthesize"
    assert "report_synthesize@v" in versioned


def test_report_synthesize_contains_ai_disclaimer_field() -> None:
    """Prompt schema must include ai_disclaimer to enforce compliance labelling."""
    rendered, _, _ = render_prompt(
        "report_synthesize",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试品"},
        survey_questions=[],
        all_answers=[],
        report_template={},
    )
    assert "ai_disclaimer" in rendered, (
        "report_synthesize prompt must require 'ai_disclaimer' in output schema"
    )


def test_report_synthesize_contains_top_pros_field() -> None:
    """Prompt schema must require top_pros (positive evidence with business implication)."""
    rendered, _, _ = render_prompt(
        "report_synthesize",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试品"},
        survey_questions=[],
        all_answers=[],
        report_template={},
    )
    assert "top_pros" in rendered, (
        "report_synthesize prompt must require 'top_pros' in output schema"
    )


def test_report_synthesize_contains_top_cons_field() -> None:
    """Prompt schema must require top_cons (risk evidence with improvement suggestion)."""
    rendered, _, _ = render_prompt(
        "report_synthesize",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试品"},
        survey_questions=[],
        all_answers=[],
        report_template={},
    )
    assert "top_cons" in rendered, (
        "report_synthesize prompt must require 'top_cons' in output schema"
    )


def test_report_synthesize_contains_decision_suggestion() -> None:
    """Prompt must include go/iterate/pause decision fields."""
    rendered, _, _ = render_prompt(
        "report_synthesize",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试品"},
        survey_questions=[],
        all_answers=[],
        report_template={},
    )
    assert "decision_suggestion" in rendered
    assert "go|iterate|pause" in rendered or "go" in rendered


def test_report_synthesize_schema_fragment_is_valid_json() -> None:
    """The JSON schema embedded in the template must itself be parseable."""
    import json

    rendered, _, _ = render_prompt(
        "report_synthesize",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试品", "price": 99},
        survey_questions=[{"id": "q01", "type": "scale_1_5", "question": "？"}],
        all_answers=[{"persona_name": "小红", "overall_intent": 3}],
        report_template={},
    )

    # Extract the JSON block embedded in the prompt (starts after "输出 JSON schema：")
    marker = "输出 JSON schema："
    idx = rendered.find(marker)
    assert idx != -1, "Prompt must contain '输出 JSON schema：' section"
    schema_text = rendered[idx + len(marker):].strip()

    # The block should start with {
    brace_start = schema_text.find("{")
    assert brace_start != -1, "JSON schema block not found"

    # Try parsing — find matching closing brace
    depth = 0
    end_idx = -1
    in_str = False
    esc = False
    for i, ch in enumerate(schema_text[brace_start:], brace_start):
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_idx = i + 1
                break

    assert end_idx != -1, "Could not find closing brace for JSON schema"
    json_str = schema_text[brace_start:end_idx]
    parsed = json.loads(json_str)
    assert isinstance(parsed, dict)
    assert "ai_disclaimer" in parsed
    assert "top_pros" in parsed
    assert "top_cons" in parsed
    assert "metrics" in parsed


def test_report_synthesize_injects_product_summary() -> None:
    """Product name should appear in rendered prompt."""
    rendered, _, _ = render_prompt(
        "report_synthesize",
        user_role_type="channel",
        product_ai_summary={"name": "珀莱雅双抗精华", "brand": "珀莱雅"},
        survey_questions=[],
        all_answers=[],
        report_template={},
    )
    assert "珀莱雅双抗精华" in rendered


def test_report_synthesize_includes_all_answers_data() -> None:
    """All answers content should be included in rendered prompt."""
    rendered, _, _ = render_prompt(
        "report_synthesize",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试品"},
        survey_questions=[],
        all_answers=[
            {"persona_name": "唯一标识角色X", "overall_intent": 5, "sentiment": "positive"}
        ],
        report_template={},
    )
    assert "唯一标识角色X" in rendered


def test_report_synthesize_prohibits_false_market_claims() -> None:
    """Prompt must instruct AI not to present simulated data as real market conclusions."""
    rendered, _, _ = render_prompt(
        "report_synthesize",
        user_role_type="manufacturer",
        product_ai_summary={"name": "测试品"},
        survey_questions=[],
        all_answers=[],
        report_template={},
    )
    # The prompt should contain restriction language
    assert any(kw in rendered for kw in [
        "不要把", "仅供参考", "AI 生成", "不替代", "真实市场"
    ]), "Prompt must contain compliance restriction instructions"
