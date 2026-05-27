from __future__ import annotations

from typing import cast

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.persona import Persona
from app.db.repositories.base import BaseRepository


class PersonaRepository(BaseRepository[Persona]):
    """Repository for personas."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Persona)

    async def get_by_name_and_version(self, *, name: str, version: int) -> Persona | None:
        """Return a persona by the seed idempotency key."""

        return cast(
            Persona | None,
            await self.session.scalar(
                select(Persona).where(
                    Persona.name == name,
                    Persona.version == version,
                    Persona.deleted_at.is_(None),
                )
            ),
        )

    async def list_visible_to_user(
        self,
        *,
        user_id: int,
        limit: int = 500,
    ) -> list[Persona]:
        """Return system personas and private personas owned by a user.

        ``limit`` caps the result set to prevent accidental full-table loads.
        The default of 500 comfortably covers the 1000-user launch scale
        (≈20 system personas + user-created ones).  Service-layer filtering
        and pagination are applied on top of this slice.
        """

        result = await self.session.scalars(
            select(Persona)
            .where(
                or_(Persona.owner_id.is_(None), Persona.owner_id == user_id),
                Persona.deleted_at.is_(None),
                Persona.status == "active",
            )
            .order_by(Persona.owner_id.is_not(None), Persona.created_at.desc(), Persona.id.desc())
            .limit(limit)
        )
        return list(result.all())

    async def get_active_by_id(self, *, persona_id: int) -> Persona | None:
        """Return an active, non-deleted persona by ID."""

        return cast(
            Persona | None,
            await self.session.scalar(
                select(Persona).where(
                    Persona.id == persona_id,
                    Persona.deleted_at.is_(None),
                    Persona.status == "active",
                )
            ),
        )
