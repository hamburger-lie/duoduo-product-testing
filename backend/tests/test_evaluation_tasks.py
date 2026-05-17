from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models.answer import Answer
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.survey import Survey
from app.db.models.user import User
from app.tasks.evaluation_tasks import _run_evaluation_async


@dataclass
class TaskContext:
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def task_context(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[TaskContext]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(Product.__table__.create)
        await connection.run_sync(Persona.__table__.create)
        await connection.run_sync(Evaluation.__table__.create)
        await connection.run_sync(Survey.__table__.create)
        await connection.run_sync(Answer.__table__.create)

    monkeypatch.setattr("app.db.session.AsyncSessionFactory", session_factory)

    yield TaskContext(session_factory=session_factory)

    await engine.dispose()


async def create_task_fixture(
    context: TaskContext,
    *,
    status: str = "answering",
) -> tuple[int, int, int]:
    async with context.session_factory() as session:
        user = User(openid="task_user", nickname="Task User")
        session.add(user)
        await session.flush()

        product = Product(
            user_id=user.id,
            name="异步测试产品",
            description="用于异步任务测试的产品",
            price=Decimal("99.00"),
            image_urls=[],
            ai_summary={"category": "美妆"},
            status="ready",
        )
        session.add(product)
        await session.flush()

        persona = Persona(
            owner_id=None,
            name="任务测试角色",
            avatar="person",
            age=29,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="运营",
            income_monthly=18000,
            ocean_o=60,
            ocean_c=70,
            ocean_e=50,
            ocean_a=65,
            ocean_n=45,
            persona_tag="成分党",
            profile={"bio": "关注成分和价格"},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        session.add(persona)
        await session.flush()

        evaluation = Evaluation(
            user_id=user.id,
            product_id=product.id,
            selected_persona_ids=[str(persona.id)],
            status=status,
            progress=0,
            task_id="existing-task-id",
            run_mode="celery",
        )
        session.add(evaluation)
        await session.flush()

        survey = Survey(
            evaluation_id=evaluation.id,
            product_id=product.id,
            questions=[
                {
                    "id": "q1",
                    "dim": "purchase_intent",
                    "type": "scale_1_5",
                    "question": "你愿意买吗？",
                    "options": None,
                }
            ],
            version=1,
            generated_by="ai",
        )
        session.add(survey)
        await session.flush()

        evaluation.survey_id = survey.id
        await session.commit()
        return evaluation.id, user.id, persona.id


async def test_evaluation_task_keeps_canceled_evaluation_canceled(
    task_context: TaskContext,
) -> None:
    evaluation_id, user_id, _ = await create_task_fixture(task_context, status="canceled")

    result = await _run_evaluation_async(evaluation_id, user_id, "celery-task-id")

    assert result["status"] == "canceled"
    async with task_context.session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        assert evaluation.status == "canceled"
        assert evaluation.progress == 0
        answers = (
            await session.scalars(select(Answer).where(Answer.evaluation_id == evaluation_id))
        ).all()
        assert len(answers) == 0


async def test_evaluation_task_skips_existing_answer_without_duplicate(
    task_context: TaskContext,
) -> None:
    evaluation_id, user_id, persona_id = await create_task_fixture(task_context)
    async with task_context.session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        assert evaluation.survey_id is not None
        session.add(
            Answer(
                evaluation_id=evaluation_id,
                survey_id=evaluation.survey_id,
                persona_id=persona_id,
                answers=[
                    {
                        "qid": "q1",
                        "type": "scale_1_5",
                        "answer": 4,
                        "reason": "已有答案",
                    }
                ],
                overall_intent=4,
                sentiment="positive",
                status="done",
                token_input=0,
                token_output=0,
                cost_yuan=Decimal("0.0000"),
            )
        )
        await session.commit()

    result = await _run_evaluation_async(evaluation_id, user_id, "celery-task-id")

    assert result["status"] == "done"
    async with task_context.session_factory() as session:
        answers = (
            await session.scalars(select(Answer).where(Answer.evaluation_id == evaluation_id))
        ).all()
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        assert len(answers) == 1
        assert evaluation.status == "done"
        assert evaluation.progress == 100
        assert evaluation.finished_at is not None


async def test_evaluation_task_marks_all_failed_when_persona_generation_fails(
    task_context: TaskContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluation_id, user_id, _ = await create_task_fixture(task_context)

    async def fake_generate_answer(*args: object, **kwargs: object) -> tuple[list[dict], int, str]:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(
        "app.services.evaluation_service.EvaluationService._generate_answer",
        fake_generate_answer,
    )

    result = await _run_evaluation_async(evaluation_id, user_id, "celery-task-id")

    assert result["status"] == "failed"
    async with task_context.session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        assert evaluation.status == "failed"
        assert evaluation.error_message == "All persona answers failed"
        answer = await session.scalar(select(Answer).where(Answer.evaluation_id == evaluation_id))
        assert answer is not None
        assert answer.status == "failed"
        assert answer.error_message == "model unavailable"


async def test_evaluation_task_does_not_finalize_canceled_evaluation(
    task_context: TaskContext,
) -> None:
    evaluation_id, user_id, _ = await create_task_fixture(task_context)

    async with task_context.session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        evaluation.status = "canceled"
        await session.commit()

    result = await _run_evaluation_async(evaluation_id, user_id, "celery-task-id")

    assert result["status"] == "canceled"
    async with task_context.session_factory() as session:
        evaluation = await session.get(Evaluation, evaluation_id)
        assert evaluation is not None
        assert evaluation.status == "canceled"
        assert evaluation.finished_at is None
