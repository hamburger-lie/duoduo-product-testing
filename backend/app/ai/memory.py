from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import BigInteger, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BaseModelMixin

logger = logging.getLogger(__name__)


class PersonaMemory(Base, BaseModelMixin):
    """Stores extracted persona memories for cross-conversation recall."""

    __tablename__ = "persona_memories"

    persona_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    evaluation_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    memory_type: Mapped[str] = mapped_column(String(64), nullable=False, default="preference")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=80)


@runtime_checkable
class MemoryAdapter(Protocol):
    """Protocol for persona memory storage."""

    async def add_questionnaire_memories(
        self,
        *,
        persona_id: int,
        evaluation_id: int,
        user_id: int,
        answers: list[dict[str, Any]],
        product_summary: dict[str, Any],
    ) -> int:
        """Extract and store memories from questionnaire answers. Returns count stored."""
        ...

    async def add_chat_turn(
        self,
        *,
        persona_id: int,
        evaluation_id: int,
        user_id: int,
        user_message: str,
        assistant_message: str,
        product_summary: dict[str, Any],
    ) -> int:
        """Extract and store memories from a conversation turn. Returns count stored."""
        ...

    async def search(
        self,
        *,
        persona_id: int,
        evaluation_id: int,
        user_id: int,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for relevant memories."""
        ...


class DatabaseMemoryAdapter:
    """Database-backed memory adapter using AI extraction.

    Stores memories in PostgreSQL. For MVP this provides
    cross-conversation persona memory without requiring Qdrant.
    Can be replaced with a vector-backed adapter later.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_questionnaire_memories(
        self,
        *,
        persona_id: int,
        evaluation_id: int,
        user_id: int,
        answers: list[dict[str, Any]],
        product_summary: dict[str, Any],
    ) -> int:
        """Extract memories from questionnaire answers using AI."""

        memories = await self._extract_memories(
            persona_id=persona_id,
            product_summary=product_summary,
            messages=[
                {"role": "system", "content": "问卷答题结果"},
                {"role": "assistant", "content": json.dumps(answers, ensure_ascii=False)[:2000]},
            ],
        )
        count = 0
        for mem in memories:
            self._session.add(
                PersonaMemory(
                    persona_id=persona_id,
                    evaluation_id=evaluation_id,
                    user_id=user_id,
                    memory_type=mem.get("type", "preference"),
                    content=mem.get("memory", ""),
                    confidence=int(mem.get("confidence", 0.8) * 100),
                )
            )
            count += 1
        if count:
            await self._session.flush()
            logger.info(
                "memories_stored_from_questionnaire persona_id=%d count=%d",
                persona_id,
                count,
            )
        return count

    async def add_chat_turn(
        self,
        *,
        persona_id: int,
        evaluation_id: int,
        user_id: int,
        user_message: str,
        assistant_message: str,
        product_summary: dict[str, Any],
    ) -> int:
        """Extract memories from a conversation turn using AI."""

        memories = await self._extract_memories(
            persona_id=persona_id,
            product_summary=product_summary,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": assistant_message},
            ],
        )
        count = 0
        for mem in memories:
            self._session.add(
                PersonaMemory(
                    persona_id=persona_id,
                    evaluation_id=evaluation_id,
                    user_id=user_id,
                    memory_type=mem.get("type", "preference"),
                    content=mem.get("memory", ""),
                    confidence=int(mem.get("confidence", 0.8) * 100),
                )
            )
            count += 1
        if count:
            await self._session.flush()
            logger.info(
                "memories_stored_from_chat persona_id=%d count=%d",
                persona_id,
                count,
            )
        return count

    async def search(
        self,
        *,
        persona_id: int,
        evaluation_id: int,
        user_id: int,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search memories by persona + evaluation. MVP uses simple DB query."""

        stmt = (
            select(PersonaMemory)
            .where(
                PersonaMemory.persona_id == persona_id,
                PersonaMemory.evaluation_id == evaluation_id,
                PersonaMemory.user_id == user_id,
                PersonaMemory.deleted_at.is_(None),
            )
            .order_by(PersonaMemory.confidence.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "memory": row.content,
                "type": row.memory_type,
                "confidence": row.confidence / 100.0,
            }
            for row in rows
        ]

    async def _extract_memories(
        self,
        *,
        persona_id: int,
        product_summary: dict[str, Any],
        messages: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Use AI to extract memories, or return empty on failure."""

        from app.core.config import get_settings

        if get_settings().ai_provider != "ark":
            return []

        try:
            from app.ai.factory import get_ai_client
            from app.ai.json_utils import parse_json_response
            from app.ai.models import ModelRouter, TaskType
            from app.ai.prompt_manager import render_prompt
            from app.db.repositories.persona import PersonaRepository

            persona_repo = PersonaRepository(self._session)
            persona = await persona_repo.get_active_by_id(persona_id=persona_id)
            persona_dict: dict[str, Any] = {}
            if persona:
                persona_dict = {
                    "name": persona.name,
                    "age": persona.age,
                    "persona_tag": persona.persona_tag or "",
                }

            prompt, _, _ = render_prompt(
                "memory_extract",
                persona=persona_dict,
                product_ai_summary=product_summary,
                messages=messages,
            )

            route = ModelRouter().get(TaskType.MEMORY_EXTRACT)
            ai_client = get_ai_client()
            raw = await ai_client.complete_json(
                system="你是角色记忆抽取器。只返回JSON。",
                user=prompt,
                endpoint_id=route.endpoint_id,
            )
            data = parse_json_response(raw)
            memories = data.get("memories", [])
            if isinstance(memories, list):
                return [m for m in memories if isinstance(m, dict) and m.get("memory")]
        except Exception:
            logger.exception("memory_extraction_failed persona_id=%d", persona_id)

        return []


class NoopMemoryAdapter:
    """No-op adapter for testing."""

    async def add_questionnaire_memories(self, **kwargs: Any) -> int:
        """No-op."""
        return 0

    async def add_chat_turn(self, **kwargs: Any) -> int:
        """No-op."""
        return 0

    async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        """No-op."""
        return []
