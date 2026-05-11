from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.prompt_version import PromptVersion
from app.db.repositories.base import BaseRepository


class PromptVersionRepository(BaseRepository[PromptVersion]):
    """Repository for prompt versions."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=PromptVersion)

