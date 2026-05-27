from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Unified API error response schema."""

    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: Any = None
    request_id: str
    timestamp: str
