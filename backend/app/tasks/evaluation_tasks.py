from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from time import perf_counter

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
        "evaluation_task_started",
        extra={
            "event": "evaluation_task_started",
            "evaluation_id": evaluation_id,
            "user_id": user_id,
            "task_id": str(self.request.id),
        },
    )
    return _run_async(_run_evaluation_async(evaluation_id, user_id, str(self.request.id)))


async def _run_evaluation_async(
    evaluation_id: int,
    user_id: int,
    task_id: str,
) -> dict[str, object]:
    """Async implementation of the evaluation run."""

    from app.db.session import AsyncSessionFactory

    task_started_at = perf_counter()
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
            logger.error(
                "evaluation_task_failed",
                extra={
                    "event": "evaluation_task_failed",
                    "evaluation_id": evaluation_id,
                    "user_id": user_id,
                    "task_id": task_id,
                    "duration_ms": int((perf_counter() - task_started_at) * 1000),
                    "error_code": "EVALUATION_NOT_FOUND",
                    "error_message": "Evaluation not found",
                },
            )
            return {"status": "error", "message": "Evaluation not found"}

        if evaluation.status == "canceled":
            logger.info(
                "evaluation_task_canceled",
                extra={
                    "event": "evaluation_task_canceled",
                    "evaluation_id": evaluation_id,
                    "user_id": user_id,
                    "task_id": task_id,
                    "from_status": "canceled",
                    "to_status": "canceled",
                    "duration_ms": int((perf_counter() - task_started_at) * 1000),
                },
            )
            return {"status": "canceled"}

        if evaluation.task_id is None:
            evaluation.task_id = task_id
        evaluation.run_mode = evaluation.run_mode or "celery"
        if evaluation.status != "answering":
            evaluation.status = "answering"
        evaluation.error_message = None
        await session.commit()

        survey = await surveys.get_by_id(evaluation.survey_id) if evaluation.survey_id else None
        if survey is None:
            logger.error(
                "evaluation_task_failed",
                extra={
                    "event": "evaluation_task_failed",
                    "evaluation_id": evaluation_id,
                    "user_id": user_id,
                    "task_id": task_id,
                    "duration_ms": int((perf_counter() - task_started_at) * 1000),
                    "error_code": "SURVEY_NOT_FOUND",
                    "error_message": "Survey not found",
                },
            )
            evaluation.status = "failed"
            evaluation.error_message = "Survey not found"
            evaluation.finished_at = datetime.now(UTC)
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

        total = len(evaluation.selected_persona_ids)
        completed = 0
        failed_count = 0

        try:
            for persona_id in evaluation.selected_persona_ids:
                refreshed = await evaluations.get_by_id(evaluation_id)
                if refreshed and refreshed.status == "canceled":
                    logger.info(
                        "evaluation_task_canceled",
                        extra={
                            "event": "evaluation_task_canceled",
                            "evaluation_id": evaluation_id,
                            "user_id": user_id,
                            "task_id": task_id,
                            "from_status": "answering",
                            "to_status": "canceled",
                            "duration_ms": int((perf_counter() - task_started_at) * 1000),
                        },
                    )
                    return {"status": "canceled", "completed": completed, "total": total}
                if refreshed is not None:
                    evaluation = refreshed

                persona_id_int = int(persona_id)
                existing = await answers.get_by_evaluation_and_persona(
                    evaluation_id=evaluation.id,
                    persona_id=persona_id_int,
                )
                if existing is not None:
                    if existing.status == "failed":
                        failed_count += 1
                    completed += 1
                    evaluation.progress = int(completed / total * 100) if total else 100
                    await session.commit()
                    continue

                persona = await personas.get_active_by_id(persona_id=persona_id_int)
                if persona is None:
                    failed_count += 1
                    completed += 1
                    await answers.create(
                        {
                            "evaluation_id": evaluation.id,
                            "survey_id": survey.id,
                            "persona_id": persona_id_int,
                            "answers": [],
                            "overall_intent": None,
                            "sentiment": "neutral",
                            "status": "failed",
                            "error_message": "Persona not found",
                            "token_input": 0,
                            "token_output": 0,
                            "cost_yuan": 0,
                        }
                    )
                    evaluation.progress = int(completed / total * 100) if total else 100
                    await session.commit()
                    continue

                try:
                    persona_started_at = perf_counter()
                    logger.info(
                        "evaluation_persona_started",
                        extra={
                            "event": "evaluation_persona_started",
                            "evaluation_id": evaluation.id,
                            "user_id": user_id,
                            "task_id": task_id,
                            "persona_id": persona_id_int,
                        },
                    )
                    from app.services.evaluation_service import EvaluationService

                    svc = EvaluationService(session)
                    (
                        answer_data,
                        overall_intent,
                        sentiment,
                        summary_comment,
                        thinking_process,
                    ) = await svc._generate_answer(
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
                            "summary_comment": summary_comment,
                            "thinking_process": thinking_process,
                            "status": "done",
                            "token_input": 0,
                            "token_output": 0,
                            "cost_yuan": 0,
                        }
                    )
                    logger.info(
                        "evaluation_persona_finished",
                        extra={
                            "event": "evaluation_persona_finished",
                            "evaluation_id": evaluation.id,
                            "user_id": user_id,
                            "task_id": task_id,
                            "persona_id": persona_id_int,
                            "duration_ms": int((perf_counter() - persona_started_at) * 1000),
                        },
                    )
                except Exception as exc:
                    failed_count += 1
                    logger.exception(
                        "evaluation_persona_failed",
                        extra={
                            "event": "evaluation_persona_failed",
                            "evaluation_id": evaluation.id,
                            "user_id": user_id,
                            "task_id": task_id,
                            "persona_id": persona_id_int,
                            "duration_ms": int((perf_counter() - persona_started_at) * 1000),
                            "error_message": str(exc)[:200],
                        },
                    )
                    await answers.create(
                        {
                            "evaluation_id": evaluation.id,
                            "survey_id": survey.id,
                            "persona_id": persona_id_int,
                            "answers": [],
                            "overall_intent": None,
                            "sentiment": "neutral",
                            "status": "failed",
                            "error_message": str(exc)[:200],
                            "token_input": 0,
                            "token_output": 0,
                            "cost_yuan": 0,
                        }
                    )

                completed += 1
                evaluation.progress = int(completed / total * 100) if total else 100
                await session.commit()

            refreshed = await evaluations.get_by_id(evaluation_id)
            if refreshed and refreshed.status == "canceled":
                return {"status": "canceled", "completed": completed, "total": total}
            if refreshed is not None:
                evaluation = refreshed

            _finalize_evaluation(
                evaluation,
                total=total,
                failed_count=failed_count,
            )
            await session.commit()

            logger.info(
                "evaluation_finalized",
                extra={
                    "event": "evaluation_finalized",
                    "evaluation_id": evaluation_id,
                    "user_id": user_id,
                    "task_id": task_id,
                    "to_status": evaluation.status,
                    "duration_ms": int((perf_counter() - task_started_at) * 1000),
                },
            )
            return {
                "status": evaluation.status,
                "completed": completed,
                "failed": failed_count,
                "total": total,
            }
        except Exception as exc:
            logger.exception(
                "evaluation_task_failed",
                extra={
                    "event": "evaluation_task_failed",
                    "evaluation_id": evaluation_id,
                    "user_id": user_id,
                    "task_id": task_id,
                    "duration_ms": int((perf_counter() - task_started_at) * 1000),
                    "error_message": str(exc)[:200],
                },
            )
            refreshed = await evaluations.get_by_id(evaluation_id)
            if refreshed is not None and refreshed.status != "canceled":
                refreshed.status = "failed"
                refreshed.error_message = str(exc)[:200]
                refreshed.finished_at = datetime.now(UTC)
                await session.commit()
            return {"status": "failed", "message": str(exc)[:200]}


def _finalize_evaluation(
    evaluation: object,
    *,
    total: int,
    failed_count: int,
) -> None:
    """Finalize a completed evaluation task using the existing status policy."""

    from app.db.models.evaluation import Evaluation

    assert isinstance(evaluation, Evaluation)
    evaluation.progress = 100 if total else 0
    evaluation.status = "failed" if failed_count >= total and total > 0 else "done"
    evaluation.finished_at = datetime.now(UTC)
    evaluation.error_message = (
        "All persona answers failed" if evaluation.status == "failed" else None
    )
