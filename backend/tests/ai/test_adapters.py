from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from app.ai.client import MockAIClient
from app.ai.exceptions import AIResponseInvalid
from app.schemas.product import ProductCreateRequest


class _GoodProductClient(MockAIClient):
    async def complete_json(self, *, system: str, user: str, endpoint_id: str) -> str:
        return json.dumps(
            {
                "main_selling_points": ["温和修护"],
                "key_ingredients_or_features": ["烟酰胺"],
                "suitable_skin_types_or_users": ["敏感肌"],
                "target_audience": "都市护肤用户",
                "competitive_position": "中端",
            }
        )


class _GoodSurveyClient(MockAIClient):
    """Returns one valid 15-question batch per call (survey is 2 batches)."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def complete_json(
        self, *, system: str, user: str, endpoint_id: str, **kwargs: object
    ) -> str:
        self.prompts.append(user)
        return json.dumps(
            {
                "questions": [
                    {
                        "id": f"q{i:02d}",
                        "dim": "first_impression",
                        "type": "scale_1_5",
                        "question": f"问题 {i}",
                        "options": None,
                    }
                    for i in range(1, 16)
                ]
            }
        )


class _GoodPersonaClient(MockAIClient):
    async def complete_json(self, *, system: str, user: str, endpoint_id: str) -> str:
        return json.dumps(
            {
                "overall_intent": 4,
                "sentiment": "positive",
                "answers": [
                    {
                        "qid": "q01",
                        "type": "scale_1_5",
                        "answer": 4,
                        "reason_short": "值得买",
                    }
                ],
                "summary_comment": "整体愿意尝试",
            }
        )


class _BadSurveyClient(MockAIClient):
    async def complete_json(
        self, *, system: str, user: str, endpoint_id: str, **kwargs: object
    ) -> str:
        return json.dumps({"questions": []})


def _fake_product() -> Any:
    class _Product:
        id = 1
        name = "测试面霜"
        description = "一款测试护肤品"
        category = "护肤"
        brand = "TestBrand"
        price = None
        ai_summary: dict[str, object] | None = None

    return _Product()


def _fake_survey() -> Any:
    class _Survey:
        questions: list[dict[str, object]] = [
            {"id": "q01", "type": "scale_1_5", "question": "整体印象？", "options": None}
        ]

    return _Survey()


def _fake_persona() -> Any:
    class _Persona:
        id = 1
        name = "测试用户"
        age = 28
        city = "上海"
        occupation = "白领"
        persona_tag = "精致妈妈"
        is_critical = False
        profile: dict[str, object] = {}

    return _Persona()


@pytest.mark.asyncio
async def test_product_understanding_adapter_normalizes_ai_fields() -> None:
    from app.ai.adapters.structured_generation import ProductUnderstandingAdapter

    adapter = ProductUnderstandingAdapter(ai_client=_GoodProductClient())
    summary = await adapter.generate_summary(
        payload=ProductCreateRequest(
            name="测试面霜",
            description="添加烟酰胺和神经酰胺，主打温和修护和提亮。",
            image_object_keys=["products/front.jpg"],
            price=Decimal("199.00"),
        )
    )

    assert summary.key_ingredients == ["烟酰胺"]
    assert summary.suitable_skin_types == ["敏感肌"]


@pytest.mark.asyncio
async def test_survey_generation_adapter_returns_valid_questions() -> None:
    from app.ai.adapters.structured_generation import SurveyGenerationAdapter

    client = _GoodSurveyClient()
    adapter = SurveyGenerationAdapter(ai_client=client)
    questions = await adapter.generate_questions(product=_fake_product(), extra_focus=None)

    assert len(questions) == 30
    assert questions[0]["id"] == "q01"
    # Two parallel batch calls, each rendered with its own half of the survey
    assert len(client.prompts) == 2
    assert any("q01-q15" in p for p in client.prompts)
    assert any("q16-q30" in p for p in client.prompts)


@pytest.mark.asyncio
async def test_survey_generation_adapter_renumbers_and_fixes_batch2_dims() -> None:
    from app.ai.adapters.structured_generation import SurveyGenerationAdapter

    adapter = SurveyGenerationAdapter(ai_client=_GoodSurveyClient())
    questions = await adapter.generate_questions(product=_fake_product(), extra_focus=None)

    # Ids are renumbered positionally q01-q30 even if batch 2 misnumbers
    assert [q["id"] for q in questions] == [f"q{i:02d}" for i in range(1, 31)]
    # Mock returns first_impression for all — invalid for batch 2, so the
    # adapter falls back to the positional dim contract (3 questions per dim)
    assert questions[15]["dim"] == "usage_scenario"
    assert questions[29]["dim"] == "painpoint_improvement"


@pytest.mark.asyncio
async def test_survey_generation_adapter_rejects_wrong_question_count() -> None:
    from app.ai.adapters.structured_generation import SurveyGenerationAdapter

    adapter = SurveyGenerationAdapter(ai_client=_BadSurveyClient())

    with pytest.raises(AIResponseInvalid, match="15"):
        await adapter.generate_questions(product=_fake_product(), extra_focus=None)


@pytest.mark.asyncio
async def test_persona_answer_adapter_returns_normalized_tuple() -> None:
    from app.ai.adapters.structured_generation import PersonaAnswerGenerationAdapter

    adapter = PersonaAnswerGenerationAdapter(ai_client=_GoodPersonaClient())
    answers, intent, sentiment, summary_comment, thinking_process = await adapter.generate_answer(
        survey=_fake_survey(),
        persona=_fake_persona(),
        product_summary={"id": 1, "name": "面霜"},
    )

    assert answers == [
        {"qid": "q01", "type": "scale_1_5", "answer": 4, "reason": "值得买"}
    ]
    assert intent == 4
    assert sentiment == "positive"
    assert summary_comment == "整体愿意尝试"
    assert thinking_process is None
