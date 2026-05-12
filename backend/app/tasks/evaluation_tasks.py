from __future__ import annotations

import asyncio
import logging

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro: object) -> dict[str, object]:
    """Run an async coroutine from synchronous Celery worker context."""

    loop = asyncio.new_event_loop()
    try:
        result: dict[str, object] = loop.run_until_complete(coro)  # type: ignore[arg-type]
        return result
    finally:
        loop.close()


@celery_app.task(bind=True, name="evaluation.run", max_retries=0)  # type: ignore[untyped-decorator]
def run_evaluation_task(self: object, evaluation_id: int, user_id: int) -> dict[str, object]:
    """Celery task that runs evaluation answering asynchronously."""

    from celery import Task  # type: ignore[import-untyped]

    assert isinstance(self, Task)
    logger.info(
        "celery_evaluation_start evaluation_id=%d user_id=%d task_id=%s",
        evaluation_id,
        user_id,
        self.request.id,
    )
    return _run_async(_run_evaluation_async(evaluation_id, user_id, str(self.request.id)))


async def _run_evaluation_async(
    evaluation_id: int,
    user_id: int,
    task_id: str,
) -> dict[str, object]:
    """Async implementation of the evaluation run."""

    from app.ai.factory import get_ai_client
    from app.core.config import get_settings
    from app.db.session import AsyncSessionFactory

    async with AsyncSessionFactory() as session:
        from app.db.repositories.answer import AnswerRepository
        from app.db.repositories.evaluation import EvaluationRepository
        from app.db.repositories.persona import PersonaRepository
        from app.db.repositories.product import ProductRepository
        from app.db.repositories.survey import SurveyRepository

        evaluations = EvaluationRepository(session)
        products = ProductRepository(session)
        personas = PersonaRepository(session)
        surveys = SurveyRepository(session)
        answers = AnswerRepository(session)

        evaluation = await evaluations.get_by_id(evaluation_id)
        if evaluation is None or evaluation.user_id != user_id:
            logger.error("celery_evaluation_not_found id=%d", evaluation_id)
            return {"status": "error", "message": "Evaluation not found"}

        if evaluation.status == "canceled":
            logger.info("celery_evaluation_already_canceled id=%d", evaluation_id)
            return {"status": "canceled"}

        survey = await surveys.get_by_id(evaluation.survey_id) if evaluation.survey_id else None
        if survey is None:
            logger.error("celery_evaluation_no_survey id=%d", evaluation_id)
            evaluation.status = "failed"
            evaluation.error_message = "Survey not found"
            await session.commit()
            return {"status": "error", "message": "Survey not found"}

        product = await products.get_by_id(evaluation.product_id)
        product_summary: dict[str, object] = {
            "id": evaluation.product_id,
            "name": product.name or "" if product else "",
            "description": product.description or "" if product else "",
        }
        if product and product.ai_summary:
            product_summary = {**product_summary, **product.ai_summary}

        s = get_settings()
        ai_client = get_ai_client() if s.ai_provider == "ark" else None

        total = len(evaluation.selected_persona_ids)
        completed = 0

        for persona_id in evaluation.selected_persona_ids:
            refreshed = await evaluations.get_by_id(evaluation_id)
            if refreshed and refreshed.status == "canceled":
                logger.info("celery_evaluation_canceled_mid_run id=%d", evaluation_id)
                return {"status": "canceled"}

            existing = await answers.get_by_evaluation_and_persona(
                evaluation_id=evaluation.id,
                persona_id=int(persona_id),
            )
            if existing is not None:
                completed += 1
                continue

            persona = await personas.get_active_by_id(persona_id=int(persona_id))
            if persona is None:
                completed += 1
                continue

            try:
                from app.services.evaluation_service import EvaluationService

                svc = EvaluationService(session, ai_client=ai_client)
                answer_data, overall_intent, sentiment = await svc._generate_answer(
                    survey=survey,
                    persona=persona,
                    product_summary=product_summary,
                )
                await answers.create(
                    {
                        "evaluation_id": evaluation.id,
                        "survey_id": survey.id,
                        "persona_id": persona.id,
                        "answers": answer_data,
                        "overall_intent": overall_intent,
                        "sentiment": sentiment,
                        "status": "done",
                        "token_input": 0,
                        "token_output": 0,
                        "cost_yuan": 0,
                    }
                )
            except Exception:
                logger.exception(
                    "celery_persona_answer_failed persona_id=%d", persona_id,
                )
                await answers.create(
                    {
                        "evaluation_id": evaluation.id,
                        "survey_id": survey.id,
                        "persona_id": int(persona_id),
                        "answers": [],
                        "overall_intent": 3,
                        "sentiment": "neutral",
                        "status": "failed",
                        "token_input": 0,
                        "token_output": 0,
                        "cost_yuan": 0,
                    }
                )

            completed += 1
            evaluation.progress = int(completed / total * 100) if total else 100
            await session.commit()

        evaluation.progress = 100
        evaluation.status = "done"
        from datetime import UTC, datetime

        evaluation.finished_at = datetime.now(UTC)
        await session.commit()

        logger.info(
            "celery_evaluation_done evaluation_id=%d completed=%d/%d",
            evaluation_id,
            completed,
            total,
        )
        return {"status": "done", "completed": completed, "total": total}
