from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvaluationCreateRequest(BaseModel):
    """Create evaluation request."""

    model_config = ConfigDict(extra="forbid")

    product_id: str


class EvaluationPersonaUpdateRequest(BaseModel):
    """Selected personas update request."""

    model_config = ConfigDict(extra="forbid")

    persona_ids: list[str] = Field(min_length=1, max_length=100)


class EvaluationStats(BaseModel):
    """Evaluation progress stats."""

    model_config = ConfigDict(extra="forbid")

    total_personas: int
    completed_personas: int
    failed_personas: int


class EvaluationResponse(BaseModel):
    """Evaluation response aligned to the API contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    product_id: str
    survey_id: str | None
    selected_persona_ids: list[str]
    status: str
    progress: int
    credit_cost: int
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error_message: str | None = None
    stats: EvaluationStats | None = None


class EvaluationRunResponse(BaseModel):
    """Synchronous mock run response."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    progress: int
    estimated_seconds: int
    task_id: str


class EvaluationListResponse(BaseModel):
    """Cursor-paginated evaluation list response."""

    model_config = ConfigDict(extra="forbid")

    items: list[EvaluationResponse]
    next_cursor: str | None
    has_more: bool


class AnswerItem(BaseModel):
    """One question answer."""

    model_config = ConfigDict(extra="forbid")

    qid: str
    type: str
    answer: int | str | list[str]
    reason: str


class EvaluationAnswerResponse(BaseModel):
    """Full answer response for one persona."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    persona_id: str
    persona_snapshot: dict[str, Any]
    overall_intent: int | None
    sentiment: str | None
    answers: list[AnswerItem]
    created_at: str


class EvaluationAnswerSummaryItem(BaseModel):
    """Answer summary item for one persona."""

    model_config = ConfigDict(extra="forbid")

    persona_id: str
    persona_name: str
    persona_tag: str | None
    overall_intent: int | None
    sentiment: str | None
