from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.conversation import Conversation, ConversationMessage
from app.db.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    """Repository for conversations."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=Conversation)

    async def get_by_user_evaluation_persona(
        self,
        *,
        user_id: int,
        evaluation_id: int,
        persona_id: int,
    ) -> Conversation | None:
        """Return active conversation for user/evaluation/persona triple."""

        return cast(
            Conversation | None,
            await self.session.scalar(
                select(Conversation).where(
                    Conversation.user_id == user_id,
                    Conversation.evaluation_id == evaluation_id,
                    Conversation.persona_id == persona_id,
                    Conversation.deleted_at.is_(None),
                )
            ),
        )

    async def get_by_id_and_user_id(
        self,
        *,
        conversation_id: int,
        user_id: int,
    ) -> Conversation | None:
        """Return one conversation owned by a user."""

        return cast(
            Conversation | None,
            await self.session.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                    Conversation.deleted_at.is_(None),
                )
            ),
        )

    async def list_by_user_id(
        self,
        *,
        user_id: int,
        evaluation_id: int | None,
        offset: int,
        limit: int,
    ) -> list[Conversation]:
        """Return conversations owned by a user."""

        query = select(Conversation).where(
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )
        if evaluation_id is not None:
            query = query.where(Conversation.evaluation_id == evaluation_id)
        result = await self.session.scalars(
            query.order_by(Conversation.created_at.desc(), Conversation.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())


class ConversationMessageRepository(BaseRepository[ConversationMessage]):
    """Repository for conversation messages."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session=session, model=ConversationMessage)

    async def list_by_conversation_id(
        self,
        *,
        conversation_id: int,
        offset: int,
        limit: int,
    ) -> list[ConversationMessage]:
        """Return messages for a conversation in chronological order."""

        result = await self.session.scalars(
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.deleted_at.is_(None),
            )
            .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def count_by_conversation_id(self, *, conversation_id: int) -> int:
        """Return total message count for a conversation."""

        from sqlalchemy import func

        result = await self.session.scalar(
            select(func.count())
            .select_from(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.deleted_at.is_(None),
            )
        )
        return int(result or 0)
