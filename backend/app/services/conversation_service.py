from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.streaming import (
    mock_sse_stream,
    split_chinese_chunks,
    sse_delta,
    sse_done,
    sse_error,
    sse_meta,
)
from app.core.exceptions import AppException
from app.db.models.conversation import Conversation, ConversationMessage
from app.db.models.user import User
from app.db.repositories.answer import AnswerRepository
from app.db.repositories.conversation import (
    ConversationMessageRepository,
    ConversationRepository,
)
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.persona import PersonaRepository
from app.db.repositories.product import ProductRepository
from app.schemas.conversation import (
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageResponse,
)

if TYPE_CHECKING:
    from app.ai.client import AIClient

MESSAGE_LIMIT = 40
RECENT_MESSAGE_COUNT = 10

logger = logging.getLogger(__name__)


class ConversationService:
    """Conversation CRUD and streaming (mock or AI)."""

    def __init__(
        self,
        session: AsyncSession,
        ai_client: AIClient | None = None,
    ) -> None:
        self.session = session
        self.conversations = ConversationRepository(session)
        self.messages = ConversationMessageRepository(session)
        self.evaluations = EvaluationRepository(session)
        self.personas = PersonaRepository(session)
        self.products = ProductRepository(session)
        self.answers = AnswerRepository(session)
        self._ai_client = ai_client

    async def create_or_get(
        self,
        *,
        user: User,
        evaluation_id: str,
        persona_id: str,
    ) -> ConversationResponse:
        """Create or return existing conversation."""

        eval_id = self._parse_id(evaluation_id, field_name="evaluation_id")
        p_id = self._parse_id(persona_id, field_name="persona_id")

        evaluation = await self.evaluations.get_by_id_and_user_id(
            evaluation_id=eval_id, user_id=user.id,
        )
        if evaluation is None:
            raise self._not_found("EVALUATION_NOT_FOUND", "Evaluation not found", evaluation_id)

        persona = await self.personas.get_active_by_id(persona_id=p_id)
        if persona is None or not self._can_use_persona(user, persona):
            raise self._not_found("PERSONA_NOT_FOUND", "Persona not found", persona_id)

        answer = await self.answers.get_by_evaluation_and_persona(
            evaluation_id=eval_id, persona_id=p_id,
        )
        if answer is None:
            raise AppException(
                code="EVALUATION_NOT_READY",
                message="No answer found for this persona in this evaluation",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={"evaluation_id": evaluation_id, "persona_id": persona_id},
            )

        existing = await self.conversations.get_by_user_evaluation_persona(
            user_id=user.id, evaluation_id=eval_id, persona_id=p_id,
        )
        if existing is not None:
            return self._to_response(existing, persona.name, persona.avatar or "")

        product = await self.products.get_by_id_and_user_id(
            product_id=evaluation.product_id, user_id=user.id,
        )
        product_name = product.name if product and product.name else "产品"
        title = f"关于{product_name}的深度访谈"

        conversation = await self.conversations.create(
            {
                "user_id": user.id,
                "evaluation_id": eval_id,
                "persona_id": p_id,
                "title": title,
                "message_count": 0,
                "last_message_at": None,
            }
        )
        await self.session.commit()
        return self._to_response(conversation, persona.name, persona.avatar or "")

    async def get_messages(
        self,
        *,
        user: User,
        conversation_id: int,
        cursor: str | None,
        limit: int,
    ) -> MessageListResponse:
        """Return paginated messages for a conversation."""

        conversation = await self._get_owned(user, conversation_id)
        offset = self._decode_cursor(cursor)
        bounded = max(1, min(limit, 100))
        rows = await self.messages.list_by_conversation_id(
            conversation_id=conversation.id, offset=offset, limit=bounded + 1,
        )
        has_more = len(rows) > bounded
        visible = rows[:bounded]
        return MessageListResponse(
            items=[self._msg_to_response(m) for m in visible],
            next_cursor=str(offset + bounded) if has_more else None,
            has_more=has_more,
        )

    async def send_message(
        self,
        *,
        user: User,
        conversation_id: int,
        content: str,
    ) -> AsyncIterator[str]:
        """Save user message and stream assistant reply (mock or AI)."""

        conversation = await self._get_owned(user, conversation_id)

        if conversation.message_count >= MESSAGE_LIMIT:
            raise AppException(
                code="CONVERSATION_LIMIT_REACHED",
                message="Conversation message limit reached",
                http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                details={"conversation_id": str(conversation_id), "limit": MESSAGE_LIMIT},
            )

        if len(content) > 500:
            raise AppException(
                code="MESSAGE_TOO_LONG",
                message="Message exceeds 500 characters",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={"length": len(content)},
            )

        from app.ai.exceptions import AIContentBlocked

        try:
            from app.ai.moderation import get_moderation_adapter

            moderator = get_moderation_adapter()
            await moderator.check_input(content)
        except (AppException, AIContentBlocked):
            raise
        except Exception:
            logger.debug("moderation_check_skipped")

        now = datetime.now(UTC)
        await self.messages.create(
            {
                "conversation_id": conversation.id,
                "role": "user",
                "content": content,
                "token_input": None,
                "token_output": None,
                "cost_yuan": None,
            }
        )
        conversation.message_count += 1
        conversation.last_message_at = now
        await self.session.flush()

        from app.core.config import get_settings

        if get_settings().ai_provider in {"ark", "deepseek"}:
            return await self._stream_ark_reply(conversation=conversation, user_content=content)

        return await self._stream_mock_reply(conversation=conversation)

    async def list_conversations(
        self,
        *,
        user: User,
        evaluation_id: str | None,
        cursor: str | None,
        limit: int,
    ) -> ConversationListResponse:
        """Return paginated conversations for a user."""

        offset = self._decode_cursor(cursor)
        bounded = max(1, min(limit, 100))
        eval_id = (
            self._parse_id(evaluation_id, field_name="evaluation_id")
            if evaluation_id
            else None
        )
        rows = await self.conversations.list_by_user_id(
            user_id=user.id, evaluation_id=eval_id, offset=offset, limit=bounded + 1,
        )
        has_more = len(rows) > bounded
        visible = rows[:bounded]
        items: list[ConversationResponse] = []
        for conv in visible:
            persona = await self.personas.get_active_by_id(persona_id=conv.persona_id)
            name = persona.name if persona else "未知"
            avatar = persona.avatar if persona else ""
            items.append(self._to_response(conv, name, avatar or ""))
        return ConversationListResponse(
            items=items,
            next_cursor=str(offset + bounded) if has_more else None,
            has_more=has_more,
        )

    async def delete_conversation(self, *, user: User, conversation_id: int) -> None:
        """Soft-delete a conversation."""

        conversation = await self._get_owned(user, conversation_id)
        await self.conversations.soft_delete(conversation)
        await self.session.commit()

    # ------------------------------------------------------------------
    # Context loading
    # ------------------------------------------------------------------

    async def _load_chat_context(
        self,
        conversation: Conversation,
    ) -> dict[str, Any]:
        """Load product, persona, answer, and recent messages for AI prompt."""

        persona = await self.personas.get_active_by_id(persona_id=conversation.persona_id)
        persona_data: dict[str, object] = {}
        if persona:
            persona_data = {
                "name": persona.name,
                "age": persona.age,
                "city": getattr(persona, "city", ""),
                "occupation": getattr(persona, "occupation", ""),
                "persona_tag": getattr(persona, "persona_tag", ""),
                "profile": persona.profile or {},
            }

        evaluation = await self.evaluations.get_by_id(conversation.evaluation_id)
        product_summary: dict[str, object] = {}
        if evaluation:
            product = await self.products.get_by_id(evaluation.product_id)
            if product:
                product_summary = {
                    "id": product.id,
                    "name": product.name or "",
                    "description": product.description or "",
                    "category": product.category or "",
                    "brand": product.brand or "",
                }
                if product.ai_summary:
                    product_summary = {**product_summary, **product.ai_summary}

        answer = await self.answers.get_by_evaluation_and_persona(
            evaluation_id=conversation.evaluation_id,
            persona_id=conversation.persona_id,
        )
        answer_history: list[dict[str, object]] = []
        if answer:
            answer_history = [
                {
                    "overall_intent": answer.overall_intent,
                    "sentiment": answer.sentiment,
                    "answers": answer.answers or [],
                }
            ]

        total = await self.messages.count_by_conversation_id(
            conversation_id=conversation.id,
        )
        offset = max(0, total - RECENT_MESSAGE_COUNT)
        recent_msgs = await self.messages.list_by_conversation_id(
            conversation_id=conversation.id,
            offset=offset,
            limit=RECENT_MESSAGE_COUNT,
        )
        history: list[dict[str, str]] = [
            {"role": m.role, "content": m.content}
            for m in recent_msgs
        ]

        return {
            "persona": persona_data,
            "product_ai_summary": product_summary,
            "persona_answer_history": answer_history,
            "conversation_history": history,
        }

    # ------------------------------------------------------------------
    # AI streaming (ark path)
    # ------------------------------------------------------------------

    async def _stream_ark_reply(
        self,
        *,
        conversation: Conversation,
        user_content: str,
    ) -> AsyncIterator[str]:
        async def _gen() -> AsyncIterator[str]:  # noqa: C901
            from app.ai.exceptions import AIError
            from app.ai.factory import get_ai_client
            from app.ai.models import ModelRouter, TaskType
            from app.ai.prompt_manager import render_prompt

            task_type = TaskType.PERSONA_CHAT
            route = ModelRouter().get(task_type)
            request_id = f"ai_req_{uuid4().hex}"
            log_extra: dict[str, object] = {
                "task_type": task_type.value,
                "endpoint_env_name": route.endpoint_env_name,
                "request_id": request_id,
                "conversation_id": str(conversation.id),
                "persona_id": str(conversation.persona_id),
                "token_input": None,
                "token_output": None,
                "error_code": None,
            }
            try:
                context = await self._load_chat_context(conversation)

                try:
                    from app.ai.memory import DatabaseMemoryAdapter

                    memory_adapter = DatabaseMemoryAdapter(self.session)
                    memories = await memory_adapter.search(
                        persona_id=conversation.persona_id,
                        evaluation_id=conversation.evaluation_id,
                        user_id=conversation.user_id,
                        query=user_content,
                    )
                    context["memory_context"] = memories
                except Exception:
                    logger.debug("memory_search_skipped")
                    context["memory_context"] = []

                prompt, _, _ = render_prompt(
                    "persona_chat",
                    **context,
                    user_message=user_content,
                )

                ai_client = self._ai_client or get_ai_client()

                system = (
                    "你是一个消费者角色扮演助手。"
                    "严格按照角色人设、问卷答案和产品信息回答。"
                    "不得改写角色年龄、职业、城市、收入、肤质、购物渠道或购买态度。"
                    "不要暴露 AI 身份。"
                )

                stream = await ai_client.stream(
                    system=system,
                    user=prompt,
                    endpoint_id=route.endpoint_id,
                )

                collected: list[str] = []
                async for chunk in stream:
                    collected.append(chunk)
                    yield sse_delta(chunk)

                full_text = "".join(collected)

                from app.ai.moderation import get_moderation_adapter

                output_moderator = get_moderation_adapter()
                await output_moderator.check_output(full_text)

                token_input = len(user_content) + len(prompt)
                token_output = len(full_text)
                cost_yuan = round((token_input + token_output) * 0.000002, 6)
                log_extra["token_input"] = token_input
                log_extra["token_output"] = token_output

                assistant_msg = await self.messages.create(
                    {
                        "conversation_id": conversation.id,
                        "role": "assistant",
                        "content": full_text,
                        "token_input": token_input,
                        "token_output": token_output,
                        "cost_yuan": cost_yuan,
                    }
                )
                conversation.message_count += 1
                conversation.last_message_at = datetime.now(UTC)
                await self.session.commit()
                logger.info("conversation_ai_stream_completed", extra=log_extra)

                try:
                    product_ctx = context.get("product_ai_summary", {})
                    await memory_adapter.add_chat_turn(
                        persona_id=conversation.persona_id,
                        evaluation_id=conversation.evaluation_id,
                        user_id=conversation.user_id,
                        user_message=user_content,
                        assistant_message=full_text,
                        product_summary=product_ctx,
                    )
                except Exception:
                    logger.exception("memory_add_chat_turn_failed")

                yield sse_meta(
                    message_id=str(assistant_msg.id),
                    token_input=token_input,
                    token_output=token_output,
                    cost_yuan=cost_yuan,
                )
                yield sse_done()

            except AIError as exc:
                log_extra["error_code"] = exc.code
                logger.exception("conversation_ai_stream_failed", extra=log_extra)
                yield sse_error(exc.code, str(exc))
                yield sse_done()
                await self.session.commit()

            except Exception:
                log_extra["error_code"] = "AI_ERROR"
                logger.exception("conversation_ai_stream_failed", extra=log_extra)
                yield sse_error("AI_ERROR", "Internal AI service error")
                yield sse_done()
                await self.session.commit()

        return _gen()

    # ------------------------------------------------------------------
    # Mock streaming (mock path)
    # ------------------------------------------------------------------

    async def _stream_mock_reply(
        self,
        *,
        conversation: Conversation,
    ) -> AsyncIterator[str]:
        assistant_text = await self._generate_mock_reply(conversation)

        token_input = 400
        token_output = len(assistant_text)
        cost_yuan = 0.0012

        assistant_msg = await self.messages.create(
            {
                "conversation_id": conversation.id,
                "role": "assistant",
                "content": assistant_text,
                "token_input": token_input,
                "token_output": token_output,
                "cost_yuan": cost_yuan,
            }
        )
        conversation.message_count += 1
        conversation.last_message_at = datetime.now(UTC)
        await self.session.commit()

        chunks = split_chinese_chunks(assistant_text)
        return mock_sse_stream(
            chunks=chunks,
            message_id=str(assistant_msg.id),
            token_input=token_input,
            token_output=token_output,
            cost_yuan=cost_yuan,
        )

    async def _generate_mock_reply(self, conversation: Conversation) -> str:
        """Generate a mock assistant reply based on persona and answer."""

        persona = await self.personas.get_active_by_id(persona_id=conversation.persona_id)
        persona_name = persona.name if persona else "角色"

        answer = await self.answers.get_by_evaluation_and_persona(
            evaluation_id=conversation.evaluation_id,
            persona_id=conversation.persona_id,
        )

        intent = answer.overall_intent if answer else 4
        reason = ""
        if answer and answer.answers:
            for item in answer.answers:
                r = item.get("reason", "")
                if r and isinstance(r, str):
                    reason = r
                    break

        evaluation = await self.evaluations.get_by_id(conversation.evaluation_id)
        product_name = "产品"
        if evaluation:
            prod = await self.products.get_by_id(evaluation.product_id)
            if prod and prod.name:
                product_name = prod.name

        reply = (
            f"我是{persona_name}。"
            f"对这款{product_name}，我当时给的是 {intent} 分。"
        )
        if reason:
            reply += f"主要是因为{reason}"
        else:
            reply += "整体来说有亮点也有改进空间。"
        return reply

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_owned(self, user: User, conversation_id: int) -> Conversation:
        """Return conversation owned by user or raise."""

        conversation = await self.conversations.get_by_id_and_user_id(
            conversation_id=conversation_id, user_id=user.id,
        )
        if conversation is None:
            raise AppException(
                code="CONVERSATION_NOT_FOUND",
                message="Conversation not found",
                http_status=status.HTTP_404_NOT_FOUND,
                details={"conversation_id": str(conversation_id)},
            )
        return conversation

    def _can_use_persona(self, user: User, persona: object) -> bool:
        """Check persona accessibility."""

        from app.db.models.persona import Persona

        assert isinstance(persona, Persona)
        return persona.owner_id is None or persona.owner_id == user.id

    def _to_response(
        self, conv: Conversation, persona_name: str, persona_avatar: str,
    ) -> ConversationResponse:
        """Convert to response schema."""

        return ConversationResponse(
            id=str(conv.id),
            evaluation_id=str(conv.evaluation_id),
            persona_id=str(conv.persona_id),
            persona_name=persona_name,
            persona_avatar=persona_avatar,
            title=conv.title or "",
            message_count=conv.message_count,
            last_message_at=self._format_dt(conv.last_message_at),
            created_at=self._format_required_dt(conv.created_at),
        )

    def _msg_to_response(self, msg: ConversationMessage) -> MessageResponse:
        """Convert message to response schema."""

        return MessageResponse(
            id=str(msg.id),
            role=msg.role,
            content=msg.content,
            created_at=self._format_required_dt(msg.created_at),
        )

    def _parse_id(self, raw_id: str, *, field_name: str) -> int:
        """Parse string ID to int."""

        if not raw_id.isdigit():
            raise AppException(
                code="VALIDATION_ERROR",
                message="ID must be a numeric string",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={field_name: raw_id},
            )
        return int(raw_id)

    def _decode_cursor(self, cursor: str | None) -> int:
        """Decode cursor to offset."""

        if cursor is None or cursor == "" or not cursor.isdigit():
            return 0
        return int(cursor)

    def _format_dt(self, value: datetime | None) -> str | None:
        """Format datetime or return None."""

        if value is None:
            return None
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    def _format_required_dt(self, value: datetime | None) -> str:
        """Format datetime, defaulting to now."""

        return self._format_dt(value) or datetime.now(UTC).isoformat().replace("+00:00", "Z")

    def _not_found(self, code: str, message: str, resource_id: str) -> AppException:
        """Build a not-found exception."""

        return AppException(
            code=code,
            message=message,
            http_status=status.HTTP_404_NOT_FOUND,
            details={"id": resource_id},
        )
