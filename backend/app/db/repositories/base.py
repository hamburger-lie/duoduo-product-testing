from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Generic, TypeVar, cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async repository with no business logic."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def get_by_id(self, entity_id: int, *, include_deleted: bool = False) -> ModelT | None:
        """Return one entity by ID."""

        id_column = cast(Any, self.model).id
        query = self._not_deleted(select(self.model), include_deleted=include_deleted).where(
            id_column == entity_id
        )
        return cast(ModelT | None, await self.session.scalar(query))

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        include_deleted: bool = False,
    ) -> list[ModelT]:
        """Return entities ordered by creation time descending."""

        created_at_column = cast(Any, self.model).created_at
        query = (
            self._not_deleted(select(self.model), include_deleted=include_deleted)
            .order_by(created_at_column.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.scalars(query)
        return list(result.all())

    async def create(self, values: dict[str, Any]) -> ModelT:
        """Create and flush an entity."""

        entity = self.model(**values)
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: ModelT, values: dict[str, Any]) -> ModelT:
        """Update and flush an entity."""

        for field, value in values.items():
            setattr(entity, field, value)
        await self.session.flush()
        return entity

    async def soft_delete(self, entity: ModelT) -> ModelT:
        """Mark an entity deleted without removing the row."""

        cast(Any, entity).deleted_at = datetime.now(UTC)
        await self.session.flush()
        return entity

    def _not_deleted(
        self,
        query: Select[tuple[ModelT]],
        *,
        include_deleted: bool,
    ) -> Select[tuple[ModelT]]:
        if include_deleted:
            return query
        deleted_at_column = cast(Any, self.model).deleted_at
        return query.where(deleted_at_column.is_(None))
