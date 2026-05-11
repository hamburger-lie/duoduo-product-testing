from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    SendMessageRequest,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)


@router.post("", response_model=ConversationResponse)
async def create_conversation(
    payload: ConversationCreateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ConversationResponse:
    """Create or retrieve a conversation for a persona in an evaluation."""

    return await ConversationService(session).create_or_get(
        user=current_user,
        evaluation_id=payload.evaluation_id,
        persona_id=payload.persona_id,
    )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    evaluation_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ConversationListResponse:
    """List conversations for the current user."""

    return await ConversationService(session).list_conversations(
        user=current_user,
        evaluation_id=evaluation_id,
        cursor=cursor,
        limit=limit,
    )


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_messages(
    conversation_id: int,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> MessageListResponse:
    """Return paginated messages for a conversation."""

    return await ConversationService(session).get_messages(
        user=current_user,
        conversation_id=conversation_id,
        cursor=cursor,
        limit=limit,
    )


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: int,
    payload: SendMessageRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> StreamingResponse:
    """Send a message and receive SSE streaming response."""

    stream = await ConversationService(session).send_message(
        user=current_user,
        conversation_id=conversation_id,
        content=payload.content,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_conversation(
    conversation_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> None:
    """Soft-delete a conversation."""

    await ConversationService(session).delete_conversation(
        user=current_user,
        conversation_id=conversation_id,
    )
