from __future__ import annotations

import json
from typing import Any

import pytest

from app.ai.client import MockAIClient
from app.ai.exceptions import AIResponseInvalid

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_valid_survey_json(n: int = 15) -> str:
    """One valid batch (the survey is generated as two 15-question batches)."""
    questions = [
        {
            "id": f"q{i:02d}",
            "dim": "first_impression",
            "type": "scale_1_5",
            "question": f"问题 {i}",
            "options": None,
            "required": True,
            "analysis_hint": "hint",
        }
        for i in range(1, n + 1)
    ]
    return json.dumps({"version": 1, "product_id": "1", "questions": questions})


def _make_valid_persona_answer_json() -> str:
    return json.dumps(
        {
            "persona_id": "1",
            "overall_intent": 4,
            "sentiment": "positive",
            "answers": [
                {"qid": "q01", "answer": 4, "reason_short": "不错", "confidence": 0.9}
            ],
            "role_consistency_notes": ["体现了该角色的消费偏好"],
        }
    )


class _GoodSurveyClient(MockAIClient):
    """MockAIClient that returns one valid 15-question batch per call."""

    async def complete_json(
        self, *, system: str, user: str, endpoint_id: str, **kwargs: object
    ) -> str:
        return _make_valid_survey_json()


class _BadJsonClient(MockAIClient):
    """MockAIClient that returns invalid JSON."""

    async def complete_json(
        self, *, system: str, user: str, endpoint_id: str, **kwargs: object
    ) -> str:
        return "this is not json at all"


class _GoodPersonaClient(MockAIClient):
    """MockAIClient that returns a valid persona answer JSON."""

    async def complete_json(self, *, system: str, user: str, endpoint_id: str) -> str:
        return _make_valid_persona_answer_json()


# ---------------------------------------------------------------------------
# Survey generator tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_survey_ark_path_returns_30_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ark_settings())

    from app.services.survey_service import SurveyService

    svc = SurveyService.__new__(SurveyService)
    svc._ai_client = _GoodSurveyClient()

    product = _fake_product()
    questions = await svc._generate_questions_with_ai(product=product, extra_focus=None)
    assert len(questions) == 30
    assert questions[0]["id"] == "q01"


@pytest.mark.asyncio
async def test_survey_ark_path_raises_on_wrong_question_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ark_settings())

    from app.services.survey_service import SurveyService

    class _Short(MockAIClient):
        async def complete_json(
            self, *, system: str, user: str, endpoint_id: str, **kwargs: object
        ) -> str:
            return _make_valid_survey_json(n=5)

    svc = SurveyService.__new__(SurveyService)
    svc._ai_client = _Short()

    with pytest.raises(AIResponseInvalid, match="15"):
        await svc._generate_questions_with_ai(product=_fake_product(), extra_focus=None)


@pytest.mark.asyncio
async def test_survey_ark_path_raises_on_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.exceptions import AIResponseInvalid as AIInvalid
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ark_settings())

    from app.services.survey_service import SurveyService

    svc = SurveyService.__new__(SurveyService)
    svc._ai_client = _BadJsonClient()

    with pytest.raises(AIInvalid):
        await svc._generate_questions_with_ai(product=_fake_product(), extra_focus=None)


# ---------------------------------------------------------------------------
# Persona answer generator tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persona_answer_ark_path_returns_valid_tuple(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ark_settings())

    from app.services.evaluation_service import EvaluationService

    svc = EvaluationService.__new__(EvaluationService)
    svc._ai_client = _GoodPersonaClient()

    (
        answers,
        intent,
        sentiment,
        summary_comment,
        thinking_process,
        input_tokens,
        output_tokens,
        cost_yuan,
    ) = await svc._generate_answer_with_ai(
        survey=_fake_survey(),
        persona=_fake_persona(),
        product_summary={"id": 1, "name": "面霜"},
    )
    assert intent == 4
    assert sentiment == "positive"
    assert isinstance(answers, list)
    assert summary_comment is None or isinstance(summary_comment, str)
    assert thinking_process is None or isinstance(thinking_process, str)


@pytest.mark.asyncio
async def test_persona_answer_ark_path_clamps_intent_to_1_5(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ark_settings())

    from app.services.evaluation_service import EvaluationService

    class _HighIntent(MockAIClient):
        async def complete_json(self, *, system: str, user: str, endpoint_id: str) -> str:
            return json.dumps(
                {
                    "persona_id": "1",
                    "overall_intent": 99,
                    "sentiment": "positive",
                    "answers": [],
                }
            )

    svc = EvaluationService.__new__(EvaluationService)
    svc._ai_client = _HighIntent()

    _, intent, _, _sc, _, _it, _ot, _cost = await svc._generate_answer_with_ai(
        survey=_fake_survey(),
        persona=_fake_persona(),
        product_summary={},
    )
    assert intent == 5


@pytest.mark.asyncio
async def test_persona_answer_invalid_json_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.exceptions import AIResponseInvalid
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ark_settings())

    from app.services.evaluation_service import EvaluationService

    svc = EvaluationService.__new__(EvaluationService)
    svc._ai_client = _BadJsonClient()

    with pytest.raises(AIResponseInvalid):
        await svc._generate_answer_with_ai(
            survey=_fake_survey(),
            persona=_fake_persona(),
            product_summary={},
        )


# ---------------------------------------------------------------------------
# Report synthesize adapter
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_report_synthesize_adapter_returns_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import config as cfg

    monkeypatch.setattr(cfg, "get_settings", lambda: _ark_settings())

    from app.ai.adapters.report_synthesize import ReportSynthesizeAdapter

    adapter = ReportSynthesizeAdapter(ai_client=MockAIClient())
    summary = await adapter.generate_summary(
        product_summary={"id": 1, "name": "面霜"},
        all_answers=[{"overall_intent": 4, "sentiment": "positive"}],
    )
    assert isinstance(summary, str)
    assert len(summary) > 0


# ---------------------------------------------------------------------------
# Stub helpers — minimal fakes without DB
# ---------------------------------------------------------------------------

class _ark_settings:
    ai_provider = "ark"
    ark_api_key = "sk-test"
    ark_base_url = "https://ark.cn-beijing.volces.com/api/v3"
    ark_ep_doubao_seed_16 = "ep-seed"
    ark_ep_doubao_15_pro_character = "ep-pro"
    ark_ep_doubao_15_lite = "ep-lite"
    ark_ep_vision_pro = "ep-vision"
    ark_ep_embedding = "ep-embed"


def _fake_product() -> Any:
    class _P:
        id = 1
        name = "测试面霜"
        description = "一款测试护肤品"
        category = "护肤"
        brand = "TestBrand"
        price = None
        ai_summary: dict[str, object] | None = None
        profile: dict[str, object] = {}

    return _P()


def _fake_survey() -> Any:
    class _S:
        id = 1
        questions: list[dict[str, object]] = [
            {"id": "q01", "type": "scale_1_5", "question": "整体印象？", "options": None}
        ]

    return _S()


def _fake_persona() -> Any:
    class _Per:
        id = 1
        name = "测试用户"
        age = 28
        city = "上海"
        occupation = "白领"
        persona_tag = "精致妈妈"
        is_critical = False
        profile: dict[str, object] = {}

    return _Per()
