from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from celery.result import AsyncResult
from celery.states import READY_STATES
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.evaluation import Evaluation
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

STALE_THRESHOLD = timedelta(minutes=30)
WATCHDOG_ERROR_MESSAGE = "Recovered by watchdog: task lost"
RUNNING_TASK_STATES = {"PENDING", "RECEIVED", "STARTED", "RETRY"}


def _run_async(coro: object) -> dict[str, object]:
    """Run an async coroutine from synchronous Celery worker context."""

    loop = asyncio.new_event_loop()
    try:
        result: dict[str, object] = loop.run_until_complete(coro)  # type: ignore[arg-type]
        return result
    finally:
        loop.close()


@celery_app.task(name="watchdog.check_stale_evaluations")  # type: ignore[untyped-decorator]
def check_stale_evaluations() -> dict[str, object]:
    """Celery Beat task that marks lost stale evaluations as failed."""

    settings = get_settings()
    if settings.app_env == "testing":
        return {"status": "skipped", "reason": "testing"}

    from app.db.session import AsyncSessionFactory

    async def _run() -> dict[str, object]:
        async with AsyncSessionFactory() as session:
            return await _recover_stale_evaluations(session)

    return _run_async(_run())


async def _recover_stale_evaluations(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    stale_threshold: timedelta = STALE_THRESHOLD,
) -> dict[str, object]:
    """Recover stale answering evaluations whose Celery task is no longer running."""

    current_time = now or datetime.now(UTC)
    cutoff = current_time - stale_threshold
    result = await session.scalars(
        select(Evaluation).where(
            Evaluation.status == "answering",
            Evaluation.deleted_at.is_(None),
            Evaluation.updated_at < cutoff,
        )
    )
    stale_evaluations = list(result.all())
    recovered = 0
    skipped = 0

    for evaluation in stale_evaluations:
        if _task_is_still_running(evaluation.task_id):
            skipped += 1
            continue

        evaluation.status = "failed"
        evaluation.error_message = WATCHDOG_ERROR_MESSAGE
        evaluation.finished_at = current_time
        logger.warning(
            "evaluation_watchdog_recovered evaluation_id=%s",
            evaluation.id,
            extra={
                "event": "evaluation_watchdog_recovered",
                "evaluation_id": evaluation.id,
                "task_id": evaluation.task_id,
            },
        )
        recovered += 1

    if recovered:
        await session.commit()

    return {
        "checked": len(stale_evaluations),
        "recovered": recovered,
        "skipped": skipped,
    }


def _task_is_still_running(task_id: str | None) -> bool:
    """Return True when Celery still reports the task as running or retrying."""

    if not task_id:
        return False

    task_state = str(AsyncResult(task_id, app=celery_app).state)
    if task_state in RUNNING_TASK_STATES:
        return True
    return task_state not in READY_STATES and task_state != "REVOKED"
