from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HistoryProductSnippet(BaseModel):
    """Minimal product info shown in history list."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    brand: str | None
    image_url: str | None  # first image, or None


class HistorySurveySnippet(BaseModel):
    """Minimal survey info shown in history list."""

    model_config = ConfigDict(extra="forbid")

    id: str
    question_count: int
    version: int


class HistoryReportSnippet(BaseModel):
    """Minimal report info shown in history list."""

    model_config = ConfigDict(extra="forbid")

    id: str
    summary: str | None  # first ~100 chars of the report summary


class HistoryItem(BaseModel):
    """One row in the history list — one completed (or in-progress) evaluation."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    created_at: str
    status: str                   # pending / running / done / failed / cancelled
    progress: int                 # 0-100
    persona_count: int            # how many personas were run

    product: HistoryProductSnippet
    survey: HistorySurveySnippet | None   # None if survey not yet generated
    report: HistoryReportSnippet | None   # None if evaluation not done yet


class HistoryListResponse(BaseModel):
    """Cursor-paginated history response."""

    model_config = ConfigDict(extra="forbid")

    items: list[HistoryItem]
    next_cursor: str | None
    has_more: bool
