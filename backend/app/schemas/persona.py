from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OceanScores(BaseModel):
    """Big Five personality scores from the public API."""

    model_config = ConfigDict(extra="forbid")

    o: int = Field(ge=0, le=100)
    c: int = Field(ge=0, le=100)
    e: int = Field(ge=0, le=100)
    a: int = Field(ge=0, le=100)
    n: int = Field(ge=0, le=100)


class PersonaCreateRequest(BaseModel):
    """Private persona creation request."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=32)
    avatar: str | None = Field(default=None, max_length=64)
    age: int = Field(ge=1, le=120)
    gender: str = Field(min_length=1, max_length=8)
    city: str = Field(min_length=1, max_length=32)
    occupation: str | None = Field(default=None, max_length=64)
    income_monthly: int | None = Field(default=None, ge=0)
    persona_tag: str | None = Field(default=None, max_length=32)
    categories: list[str] = Field(min_length=1, max_length=20)
    is_critical: bool = False
    profile: dict[str, Any]
    ocean: OceanScores


class PersonaUpdateRequest(BaseModel):
    """Private persona partial update request."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=32)
    avatar: str | None = Field(default=None, max_length=64)
    age: int | None = Field(default=None, ge=1, le=120)
    gender: str | None = Field(default=None, min_length=1, max_length=8)
    city: str | None = Field(default=None, min_length=1, max_length=32)
    occupation: str | None = Field(default=None, max_length=64)
    income_monthly: int | None = Field(default=None, ge=0)
    persona_tag: str | None = Field(default=None, max_length=32)
    categories: list[str] | None = Field(default=None, min_length=1, max_length=20)
    is_critical: bool | None = None
    profile: dict[str, Any] | None = None
    ocean: OceanScores | None = None


class PersonaListItem(BaseModel):
    """Simplified persona item for lists and recommendations."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    avatar: str | None
    age: int
    gender: str
    city: str
    city_tier: int | None
    occupation: str | None
    income_monthly: int | None
    persona_tag: str | None
    categories: list[str]
    is_critical: bool
    is_system: bool


class PersonaResponse(PersonaListItem):
    """Full persona response."""

    ocean: OceanScores
    profile: dict[str, Any]
    version: int
    created_at: str


class PersonaPageResponse(BaseModel):
    """Offset-paginated persona response."""

    model_config = ConfigDict(extra="forbid")

    items: list[PersonaListItem]
    page: int
    page_size: int
    total: int
    total_pages: int
