from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for users."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=User)

    async def get_by_openid(self, openid: str) -> User | None:
        """Return one user by mock WeChat openid."""

        return cast(
            User | None,
            await self.session.scalar(
                select(User).where(
                    User.openid == openid,
                    User.deleted_at.is_(None),
                )
            ),
        )
