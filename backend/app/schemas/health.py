from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Health check response schema."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    version: str


class LiveHealthResponse(BaseModel):
    """Liveness response schema."""

    model_config = ConfigDict(extra="forbid")

    status: str


class ReadyHealthResponse(BaseModel):
    """Readiness response schema."""

    model_config = ConfigDict(extra="forbid")

    status: str
    checks: dict[str, str]
