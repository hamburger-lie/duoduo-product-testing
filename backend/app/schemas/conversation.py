from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreateRequest(BaseModel):
    """Create or retrieve a conversation."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    persona_id: str


class ConversationResponse(BaseModel):
    """Conversation detail response."""

    model_config = ConfigDict(extra="forbid")

    id: str
    evaluation_id: str
    persona_id: str
    persona_name: str
    persona_avatar: str
    title: str
    message_count: int
    last_message_at: str | None
    created_at: str


class MessageResponse(BaseModel):
    """Single chat message."""

    model_config = ConfigDict(extra="forbid")

    id: str
    role: str
    content: str
    created_at: str


class MessageListResponse(BaseModel):
    """Paginated message list."""

    model_config = ConfigDict(extra="forbid")

    items: list[MessageResponse]
    next_cursor: str | None
    has_more: bool


class ConversationListResponse(BaseModel):
    """Paginated conversation list."""

    model_config = ConfigDict(extra="forbid")

    items: list[ConversationResponse]
    next_cursor: str | None
    has_more: bool


class SendMessageRequest(BaseModel):
    """Send a message to a conversation."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=500)
