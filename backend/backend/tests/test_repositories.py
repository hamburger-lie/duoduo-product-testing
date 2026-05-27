from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.repositories import (
    AnswerRepository,
    ConversationRepository,
    CreditTransactionRepository,
    EvaluationRepository,
    PersonaRepository,
    ProductRepository,
    PromptVersionRepository,
    ReportRepository,
    SurveyRepository,
    UserRepository,
)
from app.db.repositories.base import BaseRepository


class RepositoryTestBase(DeclarativeBase):
    """Isolated metadata for repository tests."""


class RepositoryTestItem(RepositoryTestBase):
    """Tiny SQLAlchemy model used to exercise BaseRepository."""

    __tablename__ = "test_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(RepositoryTestBase.metadata.create_all)

    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


async def test_base_repository_crud_and_soft_delete(session: AsyncSession) -> None:
    repository = BaseRepository[RepositoryTestItem](session=session, model=RepositoryTestItem)

    created = await repository.create({"name": "first"})
    await session.commit()

    fetched = await repository.get_by_id(created.id)
    assert fetched is not None
    assert fetched.name == "first"

    items = await repository.list()
    assert [item.id for item in items] == [created.id]

    updated = await repository.update(created, {"name": "renamed"})
    await session.commit()
    assert updated.name == "renamed"

    await repository.soft_delete(updated)
    await session.commit()

    assert await repository.get_by_id(created.id) is None
    raw_item = await session.scalar(
        select(RepositoryTestItem).where(RepositoryTestItem.id == created.id)
    )
    assert raw_item is not None
    assert raw_item.deleted_at is not None


def test_core_repositories_can_be_instantiated(session: AsyncSession) -> None:
    repositories = [
        UserRepository(session),
        ProductRepository(session),
        PersonaRepository(session),
        EvaluationRepository(session),
        SurveyRepository(session),
        AnswerRepository(session),
        ReportRepository(session),
        ConversationRepository(session),
        CreditTransactionRepository(session),
        PromptVersionRepository(session),
    ]

    assert all(repository.session is session for repository in repositories)
