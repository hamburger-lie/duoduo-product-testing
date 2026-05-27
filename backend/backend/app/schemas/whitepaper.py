from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WhitepaperGenerateRequest(BaseModel):
    """Request payload to start whitepaper generation."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: int = Field(..., description="ID of the evaluation to attach the whitepaper to")
    product_name: str = Field(..., min_length=1, max_length=255)
    product_description: str | None = Field(default=None, max_length=8000)


class WhitepaperResponse(BaseModel):
    """Whitepaper status and markdown content."""

    model_config = ConfigDict(extra="forbid")

    id: str
    evaluation_id: str
    status: str
    progress: int = 0  # 0-100, server-computed estimate based on elapsed time
    product_name: str
    product_description: str | None = None
    markdown: str | None = None
    error_message: str | None = None
    generated_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
