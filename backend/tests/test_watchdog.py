from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import load_all_models
from app.db.models.evaluation import Evaluation


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    load_all_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Evaluation.__table__.create)

    yield factory

    await engine.dispose()


async def _create_evaluation(
    session: AsyncSession,
    *,
    status: str,
    updated_at: datetime,
    task_id: str | None = "task-lost",
) -> Evaluation:
    evaluation = Evaluation(
        user_id=1,
        product_id=1,
        selected_persona_ids=[],
        status=status,
        updated_at=updated_at,
        task_id=task_id,
    )
    session.add(evaluation)
    await session.commit()
    await session.refresh(evaluation)
    return evaluation


async def test_stale_evaluation_marked_failed(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.tasks.watchdog import _recover_stale_evaluations

    now = datetime(2026, 5, 19, 8, 0, tzinfo=UTC)
    async with session_factory() as session:
        evaluation = await _create_evaluation(
            session,
            status="answering",
            updated_at=now - timedelta(minutes=31),
        )

        with patch("app.tasks.watchdog.AsyncResult", return_value=SimpleNamespace(state="FAILURE")):
            result = await _recover_stale_evaluations(session, now=now)

        await session.refresh(evaluation)

    assert result == {"checked": 1, "recovered": 1, "skipped": 0}
    assert evaluation.status == "failed"
    assert evaluation.error_message == "Recovered by watchdog: task lost"
    assert evaluation.finished_at is not None


async def test_fresh_evaluation_not_affected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.tasks.watchdog import _recover_stale_evaluations

    now = datetime(2026, 5, 19, 8, 0, tzinfo=UTC)
    async with session_factory() as session:
        evaluation = await _create_evaluation(
            session,
            status="answering",
            updated_at=now - timedelta(minutes=5),
        )

        result = await _recover_stale_evaluations(session, now=now)

        await session.refresh(evaluation)

    assert result == {"checked": 0, "recovered": 0, "skipped": 0}
    assert evaluation.status == "answering"
    assert evaluation.error_message is None
    assert evaluation.finished_at is None


async def test_running_task_not_affected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.tasks.watchdog import _recover_stale_evaluations

    now = datetime(2026, 5, 19, 8, 0, tzinfo=UTC)
    async with session_factory() as session:
        evaluation = await _create_evaluation(
            session,
            status="answering",
            updated_at=now - timedelta(minutes=31),
            task_id="task-running",
        )

        with patch("app.tasks.watchdog.AsyncResult", return_value=SimpleNamespace(state="STARTED")):
            result = await _recover_stale_evaluations(session, now=now)

        await session.refresh(evaluation)

    assert result == {"checked": 1, "recovered": 0, "skipped": 1}
    assert evaluation.status == "answering"
    assert evaluation.error_message is None
    assert evaluation.finished_at is None


@pytest.mark.parametrize("status", ["done", "failed", "canceled"])
async def test_done_evaluation_not_affected(
    session_factory: async_sessionmaker[AsyncSession],
    status: str,
) -> None:
    from app.tasks.watchdog import _recover_stale_evaluations

    now = datetime(2026, 5, 19, 8, 0, tzinfo=UTC)
    async with session_factory() as session:
        evaluation = await _create_evaluation(
            session,
            status=status,
            updated_at=now - timedelta(hours=2),
        )

        result = await _recover_stale_evaluations(session, now=now)

        await session.refresh(evaluation)

    assert result == {"checked": 0, "recovered": 0, "skipped": 0}
    assert evaluation.status == status
    assert evaluation.error_message is None


async def test_watchdog_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    from app.tasks.watchdog import _recover_stale_evaluations

    now = datetime(2026, 5, 19, 8, 0, tzinfo=UTC)
    async with session_factory() as session:
        evaluation = await _create_evaluation(
            session,
            status="answering",
            updated_at=now - timedelta(minutes=31),
        )

        with patch("app.tasks.watchdog.AsyncResult", return_value=SimpleNamespace(state="SUCCESS")):
            first = await _recover_stale_evaluations(session, now=now)
            second = await _recover_stale_evaluations(session, now=now)

        await session.refresh(evaluation)

    assert first == {"checked": 1, "recovered": 1, "skipped": 0}
    assert second == {"checked": 0, "recovered": 0, "skipped": 0}
    assert evaluation.status == "failed"
