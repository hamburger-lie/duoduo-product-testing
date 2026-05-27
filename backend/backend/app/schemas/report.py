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


class BusinessDecisionSuggestion(BaseModel):
    """Decision suggestion for the business-facing report."""

    model_config = ConfigDict(extra="forbid")

    verdict: str
    reason: str
    confidence: float


class BusinessReportMetrics(BaseModel):
    """Flattened metrics expected by the mini-program business report page."""

    model_config = ConfigDict(extra="forbid")

    overall_intent_avg: float
    nps: int
    intent_distribution: dict[str, int]
    dimension_scores: list[DimensionRadarItem]
    price_sensitivity: list[PriceSensitivityDistItem]
    persona_segments: list[SegmentIntentItem]


class BusinessEvidenceQuote(BaseModel):
    """Short quote used as business evidence."""

    model_config = ConfigDict(extra="forbid")

    persona_name: str
    quote: str


class BusinessProItem(BaseModel):
    """Positive business finding."""

    model_config = ConfigDict(extra="forbid")

    title: str
    support_count: int
    evidence_quotes: list[BusinessEvidenceQuote]
    business_implication: str


class BusinessConItem(BaseModel):
    """Risk or weakness business finding."""

    model_config = ConfigDict(extra="forbid")

    title: str
    support_count: int
    evidence_quotes: list[BusinessEvidenceQuote]
    improvement_suggestion: str


class BusinessTargetAudience(BaseModel):
    """Audience and channel recommendations."""

    model_config = ConfigDict(extra="forbid")

    most_likely_to_buy: list[str]
    least_likely_to_buy: list[str]
    channel_recommendation: list[str]


class MarketingCopyAngle(BaseModel):
    """One marketing message angle."""

    model_config = ConfigDict(extra="forbid")

    angle: str
    suitable_segment: str
    risk_note: str


class EvidenceChain(BaseModel):
    """Evidence chain for one business conclusion."""

    model_config = ConfigDict(extra="forbid")

    evidence_type: str
    conclusion: str
    support_count: int
    source_roles: list[str]
    source_answers: list[BusinessEvidenceQuote]
    business_action: str


class DeepInsightArticleParagraph(BaseModel):
    """One labelled paragraph inside a sub-section."""

    model_config = ConfigDict(extra="forbid")

    label: str
    body: str


class DeepInsightArticleSubsection(BaseModel):
    """A numbered sub-section (e.g. (一) …) inside a chapter."""

    model_config = ConfigDict(extra="forbid")

    heading: str
    paragraphs: list[DeepInsightArticleParagraph]


class DeepInsightArticleSection(BaseModel):
    """One top-level chapter (一、二、三) of the article."""

    model_config = ConfigDict(extra="forbid")

    heading: str
    intro: str
    subsections: list[DeepInsightArticleSubsection]


class DeepInsightArticle(BaseModel):
    """Full article structure for the collapsible deep-insight block."""

    model_config = ConfigDict(extra="forbid")

    title: str
    abstract: str
    sections: list[DeepInsightArticleSection]


class BusinessReportResponse(BaseModel):
    """Business report response consumed by the mini-program."""

    model_config = ConfigDict(extra="forbid")

    id: str
    evaluation_id: str
    template_key: str
    ai_disclaimer: str
    executive_summary: list[str]
    decision_suggestion: BusinessDecisionSuggestion
    metrics: BusinessReportMetrics
    top_pros: list[BusinessProItem]
    top_cons: list[BusinessConItem]
    target_audience: BusinessTargetAudience
    marketing_copy_angles: list[MarketingCopyAngle]
    evidence_chains: list[EvidenceChain]
    next_test_recommendations: list[str]
    generated_at: str
    deep_insight_article: DeepInsightArticle | None = None


class DeepAnalysisSectionItem(BaseModel):
    """One section in the deep analysis narrative."""

    model_config = ConfigDict(extra="forbid")

    title: str
    content: str


class DeepAnalysisResponse(BaseModel):
    """Response for GET /evaluations/{id}/deep-analysis."""

    model_config = ConfigDict(extra="forbid")

    sections: list[DeepAnalysisSectionItem]
    generated_at: str


class ReportPdfListItem(BaseModel):
    """A generated PDF report visible to the current user."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    evaluation_id: str
    product_name: str
    pdf_title: str | None = None
    pdf_url: str
    generated_at: str


class ReportPdfListResponse(BaseModel):
    """List response for generated PDF reports."""

    model_config = ConfigDict(extra="forbid")

    items: list[ReportPdfListItem]


class DeleteReportPdfsRequest(BaseModel):
    """Request body for deleting generated PDF reports."""

    model_config = ConfigDict(extra="forbid")

    report_ids: list[str]


class ReportPdfUploadResponse(BaseModel):
    """Response returned after a whitepaper PDF is uploaded."""

    model_config = ConfigDict(extra="forbid")

    report_id: str
    evaluation_id: str
    pdf_url: str
