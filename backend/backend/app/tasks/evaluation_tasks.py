from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from time import perf_counter
from typing import TYPE_CHECKING

from app.tasks.celery_app import celery_app

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.persona import Persona
    from app.db.models.survey import Survey

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PersonaAnswerSuccess:
    persona_id: int
    answers: list[dict[str, object]]
    overall_intent: int
    sentiment: str
    summary_comment: str | None
    thinking_process: str | None
    token_input: int
    token_output: int
    cost_yuan: Decimal


@dataclass(frozen=True)
class _PersonaAnswerFailure:
    persona_id: int
    error_message: str


_PersonaAnswerOutcome = _PersonaAnswerSuccess | _PersonaAnswerFailure


def _run_async(coro: object) -> dict[str, object]:
    """Run an async coroutine from synchronous Celery worker context.

    Each Celery prefork worker reuses the same OS process across tasks but
    creates a new event loop per task via asyncio.new_event_loop().  The
    global SQLAlchemy AsyncEngine keeps asyncpg connections bound to the
    *previous* task's (now-closed) event loop, causing
    "got Future attached to a different loop".

    Fix: replace the global engine/session-factory singletons with freshly
    created instances bound to *this* task's event loop before running the
    coroutine, then tear them down afterwards.  NullPool disables connection
    reuse so there is nothing to leak across loop boundaries.
    """

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    import app.db.session as _session_mod  # noqa: PLC0415

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    from app.core.config import get_settings
    settings = get_settings()
    task_engine = create_async_engine(settings.database_url, poolclass=NullPool)
    task_factory = async_sessionmaker(
        bind=task_engine,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    # Temporarily replace globals so all code paths use the new engine.
    _session_mod._engine = task_engine
    _session_mod._session_factory = task_factory

    try:
        result: dict[str, object] = loop.run_until_complete(coro)  # type: ignore[arg-type]
        return result
    finally:
        try:
            loop.run_until_complete(task_engine.dispose())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)
        # Clear globals so the next task always gets a fresh engine.
        _session_mod._engine = None
        _session_mod._session_factory = None


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="evaluation.run",
    max_retries=3,
    default_retry_delay=10,
    autoretry_for=(ConnectionError, TimeoutError, OSError),
    retry_backoff=True,
    retry_backoff_max=60,
)
def run_evaluation_task(self: object, evaluation_id: int, user_id: int) -> dict[str, object]:
    """Celery task that runs evaluation answering asynchronously.

    Automatically retries up to 3 times on transient connection/timeout errors
    with exponential backoff (10s → 20s → 40s, capped at 60s).
    Business-logic failures (e.g. evaluation not found) are NOT retried.
    """

    from celery import Task

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
    result = _run_async(_run_evaluation_async(evaluation_id, user_id, str(self.request.id)))

    from app.core.metrics import record_celery_task

    task_status = str(result.get("status", "unknown"))
    record_celery_task("evaluation.run", task_status)
    return result


async def _run_evaluation_async(
    evaluation_id: int,
    user_id: int,
    task_id: str,
) -> dict[str, object]:
    """Async implementation of the evaluation run."""

    from app.core.distributed_lock import DistributedLock

    async with DistributedLock(key=f"eval:{evaluation_id}", ttl=1800) as acquired:
        if not acquired:
            logger.warning(
                "evaluation_task_skipped_duplicate",
                extra={
                    "event": "evaluation_task_skipped_duplicate",
                    "evaluation_id": evaluation_id,
                    "user_id": user_id,
                    "task_id": task_id,
                },
            )
            return {"status": "skipped", "reason": "duplicate"}
        return await _run_evaluation_locked(evaluation_id, user_id, task_id)


async def _run_evaluation_locked(
    evaluation_id: int,
    user_id: int,
    task_id: str,
) -> dict[str, object]:
    """Core evaluation logic, executed under distributed lock."""

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

        total = len(evaluation.selected_persona_ids)

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
            if evaluation.credit_cost > 0 and total > 0:
                await _refund_failed_credits(
                    session=session,
                    evaluation=evaluation,
                    user_id=user_id,
                    failed_count=total,
                    total=total,
                )
            else:
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

        completed = 0
        failed_count = 0

        try:
            personas_to_generate: list[Persona] = []
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
                    # Refund credits for uncompleted personas
                    remaining = total - completed
                    if remaining > 0 and evaluation.credit_cost > 0:
                        await _refund_failed_credits(
                            session=session,
                            evaluation=evaluation,
                            user_id=user_id,
                            failed_count=remaining,
                            total=total,
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

                personas_to_generate.append(persona)

            if personas_to_generate:
                from app.core.config import get_settings

                answer_evaluation_id = evaluation.id
                concurrency = min(
                    len(personas_to_generate),
                    max(1, get_settings().persona_answer_concurrency),
                )
                semaphore = asyncio.Semaphore(concurrency)

                async def run_limited(persona: Persona) -> _PersonaAnswerOutcome:
                    async with semaphore:
                        return await _generate_persona_answer_outcome(
                            session=session,
                            survey=survey,
                            persona=persona,
                            product_summary=product_summary,
                            evaluation_id=answer_evaluation_id,
                            user_id=user_id,
                            task_id=task_id,
                        )

                generation_tasks = [
                    asyncio.create_task(run_limited(persona))
                    for persona in personas_to_generate
                ]

                for finished_task in asyncio.as_completed(generation_tasks):
                    outcome = await finished_task
                    refreshed = await evaluations.get_by_id(evaluation_id)
                    if refreshed and refreshed.status == "canceled":
                        for pending_task in generation_tasks:
                            if not pending_task.done():
                                pending_task.cancel()
                        await asyncio.gather(*generation_tasks, return_exceptions=True)
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
                        remaining = total - completed
                        if remaining > 0 and refreshed.credit_cost > 0:
                            await _refund_failed_credits(
                                session=session,
                                evaluation=refreshed,
                                user_id=user_id,
                                failed_count=remaining,
                                total=total,
                            )
                        return {
                            "status": "canceled",
                            "completed": completed,
                            "total": total,
                        }
                    if refreshed is not None:
                        evaluation = refreshed

                    if isinstance(outcome, _PersonaAnswerSuccess):
                        await answers.create(
                            {
                                "evaluation_id": evaluation.id,
                                "survey_id": survey.id,
                                "persona_id": outcome.persona_id,
                                "answers": outcome.answers,
                                "overall_intent": outcome.overall_intent,
                                "sentiment": outcome.sentiment,
                                "summary_comment": outcome.summary_comment,
                                "thinking_process": outcome.thinking_process,
                                "status": "done",
                                "token_input": outcome.token_input,
                                "token_output": outcome.token_output,
                                "cost_yuan": outcome.cost_yuan,
                            }
                        )
                    else:
                        failed_count += 1
                        await answers.create(
                            {
                                "evaluation_id": evaluation.id,
                                "survey_id": survey.id,
                                "persona_id": outcome.persona_id,
                                "answers": [],
                                "overall_intent": None,
                                "sentiment": "neutral",
                                "status": "failed",
                                "error_message": outcome.error_message,
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
                # Refund credits for uncompleted personas
                remaining = total - completed
                if remaining > 0 and refreshed.credit_cost > 0:
                    await _refund_failed_credits(
                        session=session,
                        evaluation=refreshed,
                        user_id=user_id,
                        failed_count=remaining,
                        total=total,
                    )
                return {"status": "canceled", "completed": completed, "total": total}
            if refreshed is not None:
                evaluation = refreshed

            _finalize_evaluation(
                evaluation,
                total=total,
                failed_count=failed_count,
            )
            await session.commit()

            # Refund credits for failed personas
            if failed_count > 0 and evaluation.credit_cost > 0:
                await _refund_failed_credits(
                    session=session,
                    evaluation=evaluation,
                    user_id=user_id,
                    failed_count=failed_count,
                    total=total,
                )

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
            await _create_followup_webhook_event(evaluation_id=evaluation_id)
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
            await session.rollback()
            refreshed = await evaluations.get_by_id(evaluation_id)
            if refreshed is not None and refreshed.status != "canceled":
                refreshed.status = "failed"
                refreshed.error_message = str(exc)[:200]
                refreshed.finished_at = datetime.now(UTC)
                # Full refund on catastrophic failure
                if refreshed.credit_cost > 0:
                    await _refund_failed_credits(
                        session=session,
                        evaluation=refreshed,
                        user_id=user_id,
                        failed_count=total,
                        total=total,
                    )
                await session.commit()
                await _create_followup_webhook_event(evaluation_id=evaluation_id)

            # Push to dead letter queue for monitoring
            from app.tasks.dlq import push_to_dlq

            await push_to_dlq(
                evaluation_id=evaluation_id,
                error=str(exc)[:500],
                task_id=task_id,
            )
            return {"status": "failed", "message": str(exc)[:200]}


async def _generate_persona_answer_outcome(
    *,
    session: AsyncSession,
    survey: Survey,
    persona: Persona,
    product_summary: dict[str, object],
    evaluation_id: int,
    user_id: int,
    task_id: str,
) -> _PersonaAnswerOutcome:
    """Generate one persona answer without writing task state to the database."""

    persona_started_at = perf_counter()
    logger.info(
        "evaluation_persona_started",
        extra={
            "event": "evaluation_persona_started",
            "evaluation_id": evaluation_id,
            "user_id": user_id,
            "task_id": task_id,
            "persona_id": persona.id,
        },
    )
    try:
        from app.services.evaluation_service import EvaluationService

        svc = EvaluationService(session)
        result = await svc._generate_answer(
            survey=survey,
            persona=persona,
            product_summary=product_summary,
        )
        answer_data = result[0]
        overall_intent = result[1]
        sentiment = result[2]
        summary_comment = result[3]
        thinking_process = result[4]
        token_input = int(result[5]) if len(result) > 5 else 0
        token_output = int(result[6]) if len(result) > 6 else 0
        cost_yuan = result[7] if len(result) > 7 else Decimal("0.0000")
        if not isinstance(cost_yuan, Decimal):
            cost_yuan = Decimal(str(cost_yuan))
        logger.info(
            "evaluation_persona_finished",
            extra={
                "event": "evaluation_persona_finished",
                "evaluation_id": evaluation_id,
                "user_id": user_id,
                "task_id": task_id,
                "persona_id": persona.id,
                "duration_ms": int((perf_counter() - persona_started_at) * 1000),
            },
        )
        return _PersonaAnswerSuccess(
            persona_id=persona.id,
            answers=answer_data,
            overall_intent=overall_intent,
            sentiment=sentiment,
            summary_comment=summary_comment,
            thinking_process=thinking_process,
            token_input=token_input,
            token_output=token_output,
            cost_yuan=cost_yuan,
        )
    except Exception as exc:
        logger.exception(
            "evaluation_persona_failed",
            extra={
                "event": "evaluation_persona_failed",
                "evaluation_id": evaluation_id,
                "user_id": user_id,
                "task_id": task_id,
                "persona_id": persona.id,
                "duration_ms": int((perf_counter() - persona_started_at) * 1000),
                "error_message": str(exc)[:200],
            },
        )
        return _PersonaAnswerFailure(
            persona_id=persona.id,
            error_message=str(exc)[:200],
        )


async def _refund_failed_credits(
    *,
    session: object,
    evaluation: object,
    user_id: int,
    failed_count: int,
    total: int,
) -> None:
    """Refund credits proportional to failed personas."""

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.config import get_settings
    from app.db.models.evaluation import Evaluation
    from app.db.repositories.user import UserRepository
    from app.services.credit_service import CreditService

    assert isinstance(session, AsyncSession)
    assert isinstance(evaluation, Evaluation)

    if total <= 0 or failed_count <= 0:
        return

    cost_per_persona = get_settings().credit_cost_per_persona
    refund_amount = min(evaluation.credit_cost, cost_per_persona * failed_count)
    if refund_amount <= 0:
        return

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        logger.warning(
            "credit_refund_user_not_found",
            extra={"user_id": user_id, "evaluation_id": evaluation.id},
        )
        return

    credit_svc = CreditService(session)
    await credit_svc.refund(
        user,
        refund_amount,
        reason="refund",
        ref_type="evaluation",
        ref_id=evaluation.id,
        note=f"测评退款: {failed_count}/{total} 个人设失败, 退还 {refund_amount} 积分",
    )
    await session.commit()
    logger.info(
        "credit_refund_completed",
        extra={
            "event": "credit_refund_completed",
            "evaluation_id": evaluation.id,
            "user_id": user_id,
            "refund_amount": refund_amount,
            "failed_count": failed_count,
            "total": total,
        },
    )


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


async def _create_followup_webhook_event(*, evaluation_id: int) -> None:
    """Persist and enqueue an outbound follow-up webhook event if enabled."""

    from app.db.session import AsyncSessionFactory
    from app.services.followup_webhook_service import FollowupWebhookService
    from app.tasks.followup_webhook_tasks import deliver_followup_webhook_event_task

    async with AsyncSessionFactory() as session:
        event = await FollowupWebhookService(session).create_event_for_evaluation(
            evaluation_id=evaluation_id,
        )
        if event is None:
            return
        await session.commit()
        event_id = event.id

    try:
        deliver_followup_webhook_event_task.apply_async(
            args=[event_id],
            queue="webhooks",
        )
    except Exception as exc:
        logger.warning(
            "followup_webhook_enqueue_failed",
            extra={
                "event": "followup_webhook_enqueue_failed",
                "evaluation_id": evaluation_id,
                "webhook_event_id": event_id,
                "error_message": str(exc)[:200],
            },
        )
