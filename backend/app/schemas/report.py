from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IntentDistributionItem(BaseModel):
    """One score bucket in overall_intent distribution."""

    model_config = ConfigDict(extra="forbid")

    score: int
    count: int


class OverallIntentMetrics(BaseModel):
    """Overall intent aggregate metrics."""

    model_config = ConfigDict(extra="forbid")

    average: float
    distribution: list[IntentDistributionItem]
    nps: int


class DimensionRadarItem(BaseModel):
    """One dimension average score."""

    model_config = ConfigDict(extra="forbid")

    dim: str
    score: float


class PriceSensitivityDistItem(BaseModel):
    """One price range bucket."""

    model_config = ConfigDict(extra="forbid")

    range: str
    count: int


class PriceSensitivityMetrics(BaseModel):
    """Price sensitivity aggregate."""

    model_config = ConfigDict(extra="forbid")

    median_acceptable_price: int
    distribution: list[PriceSensitivityDistItem]


class SegmentIntentItem(BaseModel):
    """Intent by persona segment."""

    model_config = ConfigDict(extra="forbid")

    segment: str
    count: int
    avg_intent: float


class ReportMetrics(BaseModel):
    """All report metrics."""

    model_config = ConfigDict(extra="forbid")

    overall_intent: OverallIntentMetrics
    dimensions_radar: list[DimensionRadarItem]
    price_sensitivity: PriceSensitivityMetrics
    segment_intent: list[SegmentIntentItem]


class QuoteItem(BaseModel):
    """A persona quote."""

    model_config = ConfigDict(extra="forbid")

    persona_id: str
    persona_name: str
    quote: str


class ProConItem(BaseModel):
    """One pro or con entry."""

    model_config = ConfigDict(extra="forbid")

    title: str
    support_count: int
    quotes: list[QuoteItem]


class PersonaSegments(BaseModel):
    """Persona segment groupings."""

    model_config = ConfigDict(extra="forbid")

    most_positive: list[str]
    most_negative: list[str]
    highest_value: list[str]


class ReportResponse(BaseModel):
    """Full report response aligned to API contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    evaluation_id: str
    summary: str
    metrics: ReportMetrics
    top_pros: list[ProConItem]
    top_cons: list[ProConItem]
    persona_segments: PersonaSegments
    ai_disclaimer: str
    generated_at: str
    pdf_url: str | None
    share_token: str | None
