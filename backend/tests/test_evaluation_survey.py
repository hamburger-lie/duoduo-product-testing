from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.db.models.answer import Answer
from app.db.models.credit import CreditTransaction
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.survey import Survey
from app.db.models.user import User
from app.main import app
from app.routers.survey import survey_generation_progress
from app.schemas.survey import SurveyGenerateRequest
from app.services.survey_service import SurveyService


@dataclass
class EvaluationSurveyContext:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def evaluation_survey_context() -> AsyncIterator[EvaluationSurveyContext]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(Product.__table__.create)
        await connection.run_sync(Persona.__table__.create)
        await connection.run_sync(Evaluation.__table__.create)
        await connection.run_sync(Survey.__table__.create)
        await connection.run_sync(Answer.__table__.create)
        await connection.run_sync(CreditTransaction.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield EvaluationSurveyContext(client=client, session_factory=session_factory)

    app.dependency_overrides.clear()
    await engine.dispose()


async def login(context: EvaluationSurveyContext, code: str) -> str:
    response = await context.client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return str(response.json()["token"])


async def create_product(context: EvaluationSurveyContext, token: str, name: str) -> str:
    response = await context.client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "description": "添加烟酰胺和神经酰胺，主打温和修护和提亮，适合日常护肤使用。",
            "image_object_keys": ["products/2026/05/123_front.jpg"],
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def create_evaluation(
    context: EvaluationSurveyContext,
    token: str,
    product_id: str,
) -> dict[str, object]:
    response = await context.client.post(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product_id},
    )
    assert response.status_code == 200
    return response.json()


async def generate_survey(
    context: EvaluationSurveyContext,
    token: str,
    product_id: str,
    evaluation_id: str,
) -> dict[str, object]:
    response = await context.client.post(
        "/api/v1/surveys/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product_id,
            "evaluation_id": evaluation_id,
            "extra_focus": "重点关注价格敏感度",
        },
    )
    assert response.status_code == 200
    return response.json()


async def create_system_persona(
    context: EvaluationSurveyContext,
    *,
    name: str = "林雪",
    is_critical: bool = False,
) -> str:
    async with context.session_factory() as session:
        persona = Persona(
            owner_id=None,
            name=name,
            avatar="person",
            age=28,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="产品经理",
            income_monthly=25000,
            ocean_o=70,
            ocean_c=80,
            ocean_e=50,
            ocean_a=60,
            ocean_n=55,
            persona_tag="成分党",
            profile={"bio": "关注成分"},
            categories=["美妆"],
            is_critical=is_critical,
            version=1,
            status="active",
        )
        session.add(persona)
        await session.commit()
        return str(persona.id)


async def create_private_persona(
    context: EvaluationSurveyContext,
    *,
    token: str,
    name: str = "私有角色",
) -> str:
    response = await context.client.post(
        "/api/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "avatar": "person",
            "age": 35,
            "gender": "female",
            "city": "成都",
            "occupation": "全职妈妈",
            "income_monthly": 8000,
            "persona_tag": "性价比党",
            "categories": ["美妆"],
            "is_critical": False,
            "profile": {
                "bio": "重视性价比和真实口碑",
                "shopping_habits": "常在电商平台比价",
                "skincare_concerns": ["暗沉"],
                "brand_preferences": ["国货品牌"],
                "price_sensitivity": "高",
                "info_channels": ["小红书"],
                "decision_style": "看评价后决策",
                "pet_phrases": ["值不值这个价"],
                "pain_points": ["怕踩雷"],
                "lifestyle": "家庭场景为主",
            },
            "ocean": {"o": 50, "c": 60, "e": 70, "a": 65, "n": 50},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def prepare_runnable_evaluation(
    context: EvaluationSurveyContext,
    *,
    token: str,
    persona_ids: list[str] | None = None,
) -> tuple[str, str, list[str]]:
    product_id = await create_product(context, token, "运行闭环产品")
    evaluation = await create_evaluation(context, token, product_id)
    await generate_survey(context, token, product_id, str(evaluation["id"]))
    selected_ids = persona_ids or [await create_system_persona(context)]
    response = await context.client.put(
        f"/api/v1/evaluations/{evaluation['id']}/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_ids": selected_ids},
    )
    assert response.status_code == 200
    return product_id, str(evaluation["id"]), selected_ids


async def count_answers(context: EvaluationSurveyContext, evaluation_id: str) -> int:
    async with context.session_factory() as session:
        result = await session.scalars(
            select(Answer).where(Answer.evaluation_id == int(evaluation_id))
        )
        return len(result.all())


def editable_questions() -> list[dict[str, object]]:
    return [
        {
            "id": "q1",
            "dim": "first_impression",
            "type": "scale_1_5",
            "question": "整体吸引力评分是多少？",
            "options": None,
        },
        {
            "id": "q2",
            "dim": "purchase_motivation",
            "type": "single",
            "question": "最主要购买原因是什么？",
            "options": ["成分有效", "价格合适"],
        },
    ]


def test_survey_generation_progress_keeps_moving_during_long_ai_wait() -> None:
    samples = [
        survey_generation_progress(elapsed_seconds)
        for elapsed_seconds in (2, 8, 20, 45, 75, 120)
    ]

    percentages = [pct for pct, _ in samples]
    assert percentages == sorted(percentages)
    assert percentages[0] > 10
    assert percentages[-1] < 100
    assert "DeepSeek" in samples[-1][1]


def test_mock_survey_questions_fall_back_when_seed_file_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_open(self: Path, *args: object, **kwargs: object) -> object:
        raise FileNotFoundError(str(self))

    monkeypatch.setattr(Path, "open", missing_open)

    questions = SurveyService(session=None)._load_seed_questions()  # type: ignore[arg-type]

    assert len(questions) == 30
    assert questions[0]["id"] == "q1"
    assert questions[0]["type"] == "scale_1_5"


async def test_create_evaluation_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_create")
    product_id = await create_product(evaluation_survey_context, token, "自己的产品")

    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)

    assert str(evaluation["id"]).isdigit()
    assert evaluation["product_id"] == product_id
    assert evaluation["survey_id"] is None
    assert evaluation["selected_persona_ids"] == []
    assert evaluation["status"] == "pending"
    assert evaluation["progress"] == 0
    assert evaluation["credit_cost"] == 0


async def test_delete_evaluation_soft_deletes_owned_evaluation(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_delete")
    product_id = await create_product(evaluation_survey_context, token, "delete target")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)

    response = await evaluation_survey_context.client.delete(
        f"/api/v1/evaluations/{evaluation['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204
    detail = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert detail.status_code == 404
    listing = await evaluation_survey_context.client.get(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listing.status_code == 200
    assert listing.json()["items"] == []
    async with evaluation_survey_context.session_factory() as session:
        deleted = await session.get(Evaluation, int(str(evaluation["id"])))
    assert deleted is not None
    assert deleted.deleted_at is not None


async def test_create_evaluation_missing_product_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_missing_product")
    response = await evaluation_survey_context.client.post(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": "999999"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_user_cannot_create_evaluation_for_other_users_product(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    owner_token = await login(evaluation_survey_context, "mock_eval_owner")
    other_token = await login(evaluation_survey_context, "mock_eval_other")
    product_id = await create_product(evaluation_survey_context, owner_token, "别人的产品")
    response = await evaluation_survey_context.client.post(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"product_id": product_id},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_get_own_evaluation_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_get")
    product_id = await create_product(evaluation_survey_context, token, "查询测评产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    response = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == evaluation["id"]
    assert response.json()["stats"] == {
        "total_personas": 0,
        "completed_personas": 0,
        "failed_personas": 0,
    }


async def test_user_cannot_get_other_users_evaluation(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    owner_token = await login(evaluation_survey_context, "mock_eval_get_owner")
    other_token = await login(evaluation_survey_context, "mock_eval_get_other")
    product_id = await create_product(evaluation_survey_context, owner_token, "别人的测评产品")
    evaluation = await create_evaluation(evaluation_survey_context, owner_token, product_id)
    response = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EVALUATION_NOT_FOUND"


async def test_evaluation_endpoint_without_token_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    response = await evaluation_survey_context.client.post(
        "/api/v1/evaluations",
        json={"product_id": "1"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


async def test_generate_survey_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_generate")
    product_id = await create_product(evaluation_survey_context, token, "生成问卷产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)

    survey = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )

    assert str(survey["id"]).isdigit()
    assert survey["evaluation_id"] == evaluation["id"]
    assert survey["product_id"] == product_id
    assert survey["version"] == 1
    assert survey["generated_by"] == "ai"
    assert len(survey["questions"]) == 30


async def test_generate_survey_returns_timeout_when_ai_is_too_slow(
    evaluation_survey_context: EvaluationSurveyContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowAIClient:
        async def complete_json(self, **_: object) -> str:
            await asyncio.sleep(1)
            return '{"questions": []}'

    monkeypatch.setenv("AI_PROVIDER", "mock")
    get_settings.cache_clear()
    try:
        token = await login(evaluation_survey_context, "mock_survey_ai_timeout")
        product_id = await create_product(evaluation_survey_context, token, "超时兜底产品")
        evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
        me = await evaluation_survey_context.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        user = User(id=int(me.json()["id"]), openid="mock_survey_ai_timeout")
        monkeypatch.setenv("AI_PROVIDER", "deepseek")
        monkeypatch.setenv("SURVEY_AI_TIMEOUT_SECONDS", "0.01")
        get_settings.cache_clear()

        async with evaluation_survey_context.session_factory() as session:
            started = time.monotonic()
            with pytest.raises(Exception) as exc_info:
                await SurveyService(session, ai_client=SlowAIClient()).generate_survey(
                    user=user,
                    payload=SurveyGenerateRequest(
                        product_id=product_id,
                        evaluation_id=str(evaluation["id"]),
                        extra_focus="重点关注价格敏感度",
                    ),
                )
            elapsed = time.monotonic() - started
    finally:
        get_settings.cache_clear()

    assert elapsed < 0.5
    assert exc_info.value.code == "SURVEY_AI_TIMEOUT"


async def test_generate_survey_updates_evaluation_survey_id(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_updates_eval")
    product_id = await create_product(evaluation_survey_context, token, "更新测评问卷")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    survey = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )

    response = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["survey_id"] == survey["id"]


async def test_generate_survey_is_idempotent(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_idempotent")
    product_id = await create_product(evaluation_survey_context, token, "重复生成问卷")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)

    first = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )
    second = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )

    assert second["id"] == first["id"]
    async with evaluation_survey_context.session_factory() as session:
        survey_count = len((await session.scalars(select(Survey))).all())
    assert survey_count == 1


async def test_generate_survey_returns_existing_after_evaluation_started(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_existing_done")
    product_id, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    existing = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    survey_id = existing.json()["survey_id"]

    response = await evaluation_survey_context.client.post(
        "/api/v1/surveys/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product_id, "evaluation_id": evaluation_id},
    )

    assert response.status_code == 200
    assert response.json()["id"] == survey_id


async def test_generate_survey_stream_returns_existing_after_evaluation_started(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_stream_existing")
    product_id, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await evaluation_survey_context.client.post(
        "/api/v1/surveys/generate-stream",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product_id, "evaluation_id": evaluation_id},
    )

    assert response.status_code == 200
    assert '"event": "done"' in response.text


async def test_generate_survey_with_mismatched_product_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_mismatch")
    product_id = await create_product(evaluation_survey_context, token, "问卷产品 A")
    other_product_id = await create_product(evaluation_survey_context, token, "问卷产品 B")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    response = await evaluation_survey_context.client.post(
        "/api/v1/surveys/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": other_product_id, "evaluation_id": evaluation["id"]},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_user_cannot_generate_survey_for_other_users_evaluation(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    owner_token = await login(evaluation_survey_context, "mock_survey_owner")
    other_token = await login(evaluation_survey_context, "mock_survey_other")
    product_id = await create_product(evaluation_survey_context, owner_token, "别人的问卷产品")
    evaluation = await create_evaluation(evaluation_survey_context, owner_token, product_id)
    response = await evaluation_survey_context.client.post(
        "/api/v1/surveys/generate",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"product_id": product_id, "evaluation_id": evaluation["id"]},
    )

    assert response.status_code == 404
    assert response.json()["code"] in {"PRODUCT_NOT_FOUND", "EVALUATION_NOT_FOUND"}


async def test_get_survey_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_get")
    product_id = await create_product(evaluation_survey_context, token, "查询问卷产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    survey = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )
    response = await evaluation_survey_context.client.get(
        f"/api/v1/surveys/{survey['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == survey["id"]


async def test_user_cannot_get_other_users_survey(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    owner_token = await login(evaluation_survey_context, "mock_survey_get_owner")
    other_token = await login(evaluation_survey_context, "mock_survey_get_other")
    product_id = await create_product(evaluation_survey_context, owner_token, "别人的问卷")
    evaluation = await create_evaluation(evaluation_survey_context, owner_token, product_id)
    survey = await generate_survey(
        evaluation_survey_context,
        owner_token,
        product_id,
        str(evaluation["id"]),
    )
    response = await evaluation_survey_context.client.get(
        f"/api/v1/surveys/{survey['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "SURVEY_NOT_FOUND"


async def test_update_survey_questions_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_edit")
    product_id = await create_product(evaluation_survey_context, token, "编辑问卷产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    survey = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )
    response = await evaluation_survey_context.client.put(
        f"/api/v1/surveys/{survey['id']}/questions",
        headers={"Authorization": f"Bearer {token}"},
        json=editable_questions(),
    )

    assert response.status_code == 200
    assert response.json()["questions"] == editable_questions()


async def test_update_survey_questions_updates_metadata(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_edit_metadata")
    product_id = await create_product(evaluation_survey_context, token, "编辑元数据")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    survey = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )
    response = await evaluation_survey_context.client.put(
        f"/api/v1/surveys/{survey['id']}/questions",
        headers={"Authorization": f"Bearer {token}"},
        json=editable_questions(),
    )

    assert response.status_code == 200
    assert response.json()["generated_by"] == "user_edited"
    assert response.json()["version"] == 2


async def test_update_survey_questions_locked_when_answering(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_locked")
    product_id = await create_product(evaluation_survey_context, token, "锁定问卷")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    survey = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )
    async with evaluation_survey_context.session_factory() as session:
        entity = await session.get(Evaluation, int(str(evaluation["id"])))
        assert entity is not None
        entity.status = "answering"
        await session.commit()

    response = await evaluation_survey_context.client.put(
        f"/api/v1/surveys/{survey['id']}/questions",
        headers={"Authorization": f"Bearer {token}"},
        json=editable_questions(),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "SURVEY_LOCKED"


async def test_update_survey_invalid_question_type_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_bad_type")
    product_id = await create_product(evaluation_survey_context, token, "非法题型")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    survey = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )
    bad_questions = [
        {
            "id": "q1",
            "dim": "first_impression",
            "type": "rating_10",
            "question": "非法题型？",
            "options": None,
        }
    ]
    response = await evaluation_survey_context.client.put(
        f"/api/v1/surveys/{survey['id']}/questions",
        headers={"Authorization": f"Bearer {token}"},
        json=bad_questions,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_update_survey_single_or_multi_requires_options(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_survey_options_required")
    product_id = await create_product(evaluation_survey_context, token, "缺选项")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    survey = await generate_survey(
        evaluation_survey_context,
        token,
        product_id,
        str(evaluation["id"]),
    )
    bad_questions = [
        {
            "id": "q1",
            "dim": "purchase_motivation",
            "type": "single",
            "question": "缺少选项？",
            "options": [],
        }
    ]
    response = await evaluation_survey_context.client.put(
        f"/api/v1/surveys/{survey['id']}/questions",
        headers={"Authorization": f"Bearer {token}"},
        json=bad_questions,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_evaluation_and_survey_paths_are_visible_in_openapi(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    response = await evaluation_survey_context.client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/evaluations" in paths
    assert "/api/v1/evaluations/{evaluation_id}" in paths
    assert "/api/v1/evaluations/{evaluation_id}/personas" in paths
    assert "/api/v1/evaluations/{evaluation_id}/run" in paths
    assert "/api/v1/evaluations/{evaluation_id}/cancel" in paths
    assert "/api/v1/evaluations/{evaluation_id}/answers" in paths
    assert "/api/v1/evaluations/{evaluation_id}/answers/{persona_id}" in paths
    assert "/api/v1/surveys/generate" in paths
    assert "/api/v1/surveys/{survey_id}" in paths
    assert "/api/v1/surveys/{survey_id}/questions" in paths


async def test_select_personas_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_select")
    product_id = await create_product(evaluation_survey_context, token, "选角色产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    persona_id = await create_system_persona(evaluation_survey_context)
    response = await evaluation_survey_context.client.put(
        f"/api/v1/evaluations/{evaluation['id']}/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_ids": [persona_id]},
    )

    assert response.status_code == 200
    assert response.json()["selected_persona_ids"] == [persona_id]


async def test_select_missing_persona_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_select_missing")
    product_id = await create_product(evaluation_survey_context, token, "缺角色产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    response = await evaluation_survey_context.client.put(
        f"/api/v1/evaluations/{evaluation['id']}/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_ids": ["999999"]},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PERSONA_NOT_FOUND"


async def test_select_other_users_private_persona_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    owner_token = await login(evaluation_survey_context, "mock_eval_select_owner")
    other_token = await login(evaluation_survey_context, "mock_eval_select_other")
    private_persona_id = await create_private_persona(
        evaluation_survey_context,
        token=owner_token,
    )
    product_id = await create_product(evaluation_survey_context, other_token, "越权选择产品")
    evaluation = await create_evaluation(evaluation_survey_context, other_token, product_id)
    response = await evaluation_survey_context.client.put(
        f"/api/v1/evaluations/{evaluation['id']}/personas",
        headers={"Authorization": f"Bearer {other_token}"},
        json={"persona_ids": [private_persona_id]},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PERSONA_NOT_FOUND"


async def test_run_without_survey_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_run_no_survey")
    product_id = await create_product(evaluation_survey_context, token, "无问卷产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    persona_id = await create_system_persona(evaluation_survey_context)
    await evaluation_survey_context.client.put(
        f"/api/v1/evaluations/{evaluation['id']}/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_ids": [persona_id]},
    )

    response = await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation['id']}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "EVALUATION_NOT_READY"


async def test_run_without_personas_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_run_no_persona")
    product_id = await create_product(evaluation_survey_context, token, "无角色产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    await generate_survey(evaluation_survey_context, token, product_id, str(evaluation["id"]))

    response = await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation['id']}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "EVALUATION_NOT_READY"


async def test_run_success_starts_background_answering(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_run_success")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    response = await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
    assert response.json()["id"] == evaluation_id
    assert response.json()["status"] == "answering"
    assert response.json()["progress"] == 0
    assert response.json()["task_id"] == f"bg_task_{evaluation_id}"


async def test_run_celery_mode_enqueues_task_without_generating_answers(
    evaluation_survey_context: EvaluationSurveyContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_run_celery")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )

    class FakeTask:
        id = "celery-task-test-id"

    def fake_apply_async(*, args: list[int], queue: str) -> FakeTask:
        assert queue == "evaluations"
        assert args[0] == int(evaluation_id)
        return FakeTask()

    monkeypatch.setenv("EVALUATION_RUN_MODE", "celery")
    get_settings.cache_clear()
    from app.tasks.evaluation_tasks import run_evaluation_task

    monkeypatch.setattr(run_evaluation_task, "apply_async", fake_apply_async)

    try:
        response = await evaluation_survey_context.client.post(
            f"/api/v1/evaluations/{evaluation_id}/run",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["progress"] == 0
    assert body["task_id"] == "celery-task-test-id"
    assert await count_answers(evaluation_survey_context, evaluation_id) == 0

    async with evaluation_survey_context.session_factory() as session:
        entity = await session.get(Evaluation, int(evaluation_id))
        assert entity is not None
        assert entity.status == "queued"
        assert entity.progress == 0
        assert entity.task_id == "celery-task-test-id"
        assert entity.run_mode == "celery"
        assert entity.queued_at is not None


async def test_run_celery_mode_rejects_already_answering(
    evaluation_survey_context: EvaluationSurveyContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_run_celery_repeat")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    async with evaluation_survey_context.session_factory() as session:
        entity = await session.get(Evaluation, int(evaluation_id))
        assert entity is not None
        entity.status = "answering"
        entity.task_id = "existing-task-id"
        await session.commit()

    monkeypatch.setenv("EVALUATION_RUN_MODE", "celery")
    get_settings.cache_clear()
    try:
        response = await evaluation_survey_context.client.post(
            f"/api/v1/evaluations/{evaluation_id}/run",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 409
    assert response.json()["code"] == "EVALUATION_ALREADY_RUNNING"


async def test_run_success_generates_answers(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_run_answers")
    _, evaluation_id, persona_ids = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )

    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert await count_answers(evaluation_survey_context, evaluation_id) == len(persona_ids)


async def test_repeat_run_does_not_duplicate_answers(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_repeat_run")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EVALUATION_NOT_EDITABLE"
    assert await count_answers(evaluation_survey_context, evaluation_id) == 1


async def test_get_evaluation_stats_after_run(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_stats")
    personas = [
        await create_system_persona(evaluation_survey_context, name="林雪"),
        await create_system_persona(evaluation_survey_context, name="周曼", is_critical=True),
    ]
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
        persona_ids=personas,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    response = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["stats"] == {
        "total_personas": 2,
        "completed_personas": 2,
        "failed_personas": 0,
    }


async def test_get_answers_summary_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_answer_summary")
    _, evaluation_id, persona_ids = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation_id}/answers",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()[0]["persona_id"] == persona_ids[0]
    assert response.json()[0]["overall_intent"] in [1, 2, 3, 4, 5]


async def test_get_single_persona_answer_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_single_answer")
    _, evaluation_id, persona_ids = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation_id}/answers/{persona_ids[0]}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_id"] == evaluation_id
    assert body["persona_id"] == persona_ids[0]
    assert body["persona_snapshot"]["name"] == "林雪"
    assert body["answers"]


async def test_user_cannot_query_other_users_evaluation_answers(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    owner_token = await login(evaluation_survey_context, "mock_eval_answer_owner")
    other_token = await login(evaluation_survey_context, "mock_eval_answer_other")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=owner_token,
    )
    response = await evaluation_survey_context.client.get(
        f"/api/v1/evaluations/{evaluation_id}/answers",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EVALUATION_NOT_FOUND"


async def test_cancel_pending_evaluation_success(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_cancel")
    product_id = await create_product(evaluation_survey_context, token, "取消产品")
    evaluation = await create_evaluation(evaluation_survey_context, token, product_id)
    response = await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation['id']}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"


async def test_cancel_answering_evaluation_revokes_celery_task(
    evaluation_survey_context: EvaluationSurveyContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_cancel_answering")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    async with evaluation_survey_context.session_factory() as session:
        entity = await session.get(Evaluation, int(evaluation_id))
        assert entity is not None
        entity.status = "answering"
        entity.task_id = "celery-task-to-revoke"
        await session.commit()

    revoked: dict[str, object] = {}

    def fake_revoke(task_id: str, *, terminate: bool) -> None:
        revoked["task_id"] = task_id
        revoked["terminate"] = terminate

    from app.tasks.celery_app import celery_app

    monkeypatch.setattr(celery_app.control, "revoke", fake_revoke)

    response = await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "canceled"
    assert revoked == {"task_id": "celery-task-to-revoke", "terminate": False}


async def test_done_evaluation_cancel_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_cancel_done")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/cancel",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EVALUATION_NOT_EDITABLE"


async def test_failed_evaluation_can_be_run_again(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_failed_retry")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    async with evaluation_survey_context.session_factory() as session:
        evaluation = await session.get(Evaluation, int(evaluation_id))
        assert evaluation is not None
        evaluation.status = "failed"
        evaluation.progress = 100
        await session.commit()

    response = await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "done"


async def test_evaluation_list_only_returns_current_user_evaluations(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    owner_token = await login(evaluation_survey_context, "mock_eval_list_owner")
    other_token = await login(evaluation_survey_context, "mock_eval_list_other")
    owner_product_id = await create_product(evaluation_survey_context, owner_token, "我的测评")
    other_product_id = await create_product(evaluation_survey_context, other_token, "别人测评")
    owner_eval = await create_evaluation(evaluation_survey_context, owner_token, owner_product_id)
    await create_evaluation(evaluation_survey_context, other_token, other_product_id)
    response = await evaluation_survey_context.client.get(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [owner_eval["id"]]


async def test_evaluation_list_status_filter(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_list_status")
    pending_product_id = await create_product(evaluation_survey_context, token, "pending")
    await create_evaluation(evaluation_survey_context, token, pending_product_id)
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await evaluation_survey_context.client.get(
        "/api/v1/evaluations?status=done",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [item["status"] for item in response.json()["items"]] == ["done"]


async def test_selected_personas_cannot_change_after_done(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    token = await login(evaluation_survey_context, "mock_eval_select_done")
    _, evaluation_id, _ = await prepare_runnable_evaluation(
        evaluation_survey_context,
        token=token,
    )
    await evaluation_survey_context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    persona_id = await create_system_persona(evaluation_survey_context, name="新角色")
    response = await evaluation_survey_context.client.put(
        f"/api/v1/evaluations/{evaluation_id}/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_ids": [persona_id]},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "EVALUATION_NOT_EDITABLE"


async def test_run_endpoint_without_token_fails(
    evaluation_survey_context: EvaluationSurveyContext,
) -> None:
    response = await evaluation_survey_context.client.post("/api/v1/evaluations/1/run")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"
