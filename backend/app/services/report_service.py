from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.db.models.answer import Answer
from app.db.models.persona import Persona
from app.db.models.report import Report
from app.db.models.survey import Survey
from app.db.models.user import User
from app.db.repositories.answer import AnswerRepository
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.persona import PersonaRepository
from app.db.repositories.report import ReportRepository
from app.db.repositories.survey import SurveyRepository
from app.schemas.report import (
    DimensionRadarItem,
    IntentDistributionItem,
    OverallIntentMetrics,
    PersonaSegments,
    PriceSensitivityDistItem,
    PriceSensitivityMetrics,
    ProConItem,
    QuoteItem,
    ReportMetrics,
    ReportResponse,
    SegmentIntentItem,
)

AI_DISCLAIMER = "本报告由 AI 模拟生成，仅供决策参考"


class ReportService:
    """Report generation and retrieval."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.evaluations = EvaluationRepository(session)
        self.answers = AnswerRepository(session)
        self.personas = PersonaRepository(session)
        self.surveys = SurveyRepository(session)
        self.reports = ReportRepository(session)

    async def get_or_create_report(
        self,
        *,
        user: User,
        evaluation_id: int,
    ) -> ReportResponse:
        """Return existing report or generate a new one."""

        evaluation = await self.evaluations.get_by_id_and_user_id(
            evaluation_id=evaluation_id,
            user_id=user.id,
        )
        if evaluation is None:
            raise AppException(
                code="EVALUATION_NOT_FOUND",
                message="Evaluation not found",
                http_status=status.HTTP_404_NOT_FOUND,
                details={"evaluation_id": str(evaluation_id)},
            )
        if evaluation.status != "done":
            raise AppException(
                code="EVALUATION_NOT_READY",
                message="Evaluation is not done yet",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={"evaluation_id": str(evaluation_id), "status": evaluation.status},
            )

        answer_rows = await self.answers.list_by_evaluation_id(evaluation_id=evaluation.id)
        if not answer_rows:
            raise AppException(
                code="EVALUATION_NOT_READY",
                message="Evaluation has no answers",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={"evaluation_id": str(evaluation_id)},
            )

        existing = await self.reports.get_by_evaluation_id(evaluation_id=evaluation.id)
        if existing is not None:
            return await self._to_response(existing, answer_rows)

        qid_to_dim = await self._build_qid_dim_map(evaluation.survey_id)
        personas = await self._load_personas(answer_rows)

        overall_intent = self._calc_overall_intent(answer_rows)
        dimensions_radar = self._calc_dimensions_radar(answer_rows, qid_to_dim)
        price_sensitivity = self._calc_price_sensitivity(evaluation.product_id)
        segment_intent = self._calc_segment_intent(answer_rows, personas)
        top_pros = self._calc_top_pros(answer_rows, personas)
        top_cons = self._calc_top_cons(answer_rows, personas)
        persona_segments = self._calc_persona_segments(answer_rows)
        summary = self._generate_summary(answer_rows, overall_intent)

        metrics = ReportMetrics(
            overall_intent=overall_intent,
            dimensions_radar=dimensions_radar,
            price_sensitivity=price_sensitivity,
            segment_intent=segment_intent,
        )

        report = await self.reports.create(
            {
                "evaluation_id": evaluation.id,
                "summary": summary,
                "metrics": metrics.model_dump(),
                "top_pros": [p.model_dump() for p in top_pros],
                "top_cons": [c.model_dump() for c in top_cons],
                "persona_segments": persona_segments.model_dump(),
                "pdf_url": None,
                "share_token": None,
            }
        )
        await self.session.commit()
        return self._build_response(report, metrics, top_pros, top_cons, persona_segments)

    def _calc_overall_intent(self, answers: list[Answer]) -> OverallIntentMetrics:
        """Calculate overall intent average, distribution, and NPS."""

        intents = [a.overall_intent for a in answers if a.overall_intent is not None]
        if not intents:
            return OverallIntentMetrics(
                average=0.0,
                distribution=[IntentDistributionItem(score=s, count=0) for s in range(1, 6)],
                nps=0,
            )
        average = round(sum(intents) / len(intents), 1)
        dist = {s: 0 for s in range(1, 6)}
        for intent in intents:
            if 1 <= intent <= 5:
                dist[intent] += 1
        total = len(intents)
        promoters = dist[5]
        detractors = dist[1] + dist[2] + dist[3]
        nps = round((promoters / total - detractors / total) * 100)
        return OverallIntentMetrics(
            average=average,
            distribution=[IntentDistributionItem(score=s, count=dist[s]) for s in range(1, 6)],
            nps=nps,
        )

    def _calc_dimensions_radar(
        self,
        answers: list[Answer],
        qid_to_dim: dict[str, str],
    ) -> list[DimensionRadarItem]:
        """Aggregate scale_1_5 answers by dimension."""

        dim_scores: dict[str, list[float]] = defaultdict(list)
        for answer in answers:
            for item in answer.answers:
                if item.get("type") != "scale_1_5":
                    continue
                qid = str(item.get("qid", ""))
                dim = qid_to_dim.get(qid, "unknown")
                val = item.get("answer")
                if isinstance(val, (int, float)):
                    dim_scores[dim].append(float(val))
        result: list[DimensionRadarItem] = []
        for dim, scores in sorted(dim_scores.items()):
            avg = round(sum(scores) / len(scores), 1) if scores else 0.0
            result.append(DimensionRadarItem(dim=dim, score=avg))
        return result

    def _calc_price_sensitivity(self, product_id: int) -> PriceSensitivityMetrics:
        """Return mock price sensitivity based on product."""

        return PriceSensitivityMetrics(
            median_acceptable_price=159,
            distribution=[
                PriceSensitivityDistItem(range="0-100", count=2),
                PriceSensitivityDistItem(range="100-200", count=8),
                PriceSensitivityDistItem(range="200-400", count=7),
                PriceSensitivityDistItem(range="400+", count=3),
            ],
        )

    def _calc_segment_intent(
        self,
        answers: list[Answer],
        personas: dict[int, Persona],
    ) -> list[SegmentIntentItem]:
        """Aggregate intent by persona tag."""

        seg_data: dict[str, list[int]] = defaultdict(list)
        for answer in answers:
            persona = personas.get(answer.persona_id)
            tag = persona.persona_tag if persona and persona.persona_tag else "未分类"
            if answer.overall_intent is not None:
                seg_data[tag].append(answer.overall_intent)
        result: list[SegmentIntentItem] = []
        for segment, intents in sorted(seg_data.items()):
            avg = round(sum(intents) / len(intents), 1) if intents else 0.0
            result.append(SegmentIntentItem(segment=segment, count=len(intents), avg_intent=avg))
        return result

    def _calc_top_pros(
        self,
        answers: list[Answer],
        personas: dict[int, Persona],
    ) -> list[ProConItem]:
        """Extract top pros from positive/high-score answers."""

        positive = [a for a in answers if a.overall_intent is not None and a.overall_intent >= 4]
        if not positive:
            positive = answers[:1]
        quotes: list[QuoteItem] = []
        for answer in positive[:3]:
            persona = personas.get(answer.persona_id)
            name = persona.name if persona else "未知"
            quote_text = self._extract_quote(answer, positive=True)
            quotes.append(
                QuoteItem(
                    persona_id=str(answer.persona_id),
                    persona_name=name,
                    quote=quote_text,
                )
            )
        return [
            ProConItem(
                title="产品整体获得正面评价",
                support_count=len(positive),
                quotes=quotes,
            )
        ]

    def _calc_top_cons(
        self,
        answers: list[Answer],
        personas: dict[int, Persona],
    ) -> list[ProConItem]:
        """Extract top cons from critical/low-score answers."""

        negative = [a for a in answers if a.overall_intent is not None and a.overall_intent <= 3]
        if not negative:
            negative = answers[-1:]
        quotes: list[QuoteItem] = []
        for answer in negative[:3]:
            persona = personas.get(answer.persona_id)
            name = persona.name if persona else "未知"
            quote_text = self._extract_quote(answer, positive=False)
            quotes.append(
                QuoteItem(
                    persona_id=str(answer.persona_id),
                    persona_name=name,
                    quote=quote_text,
                )
            )
        return [
            ProConItem(
                title="部分角色对产品持保留态度",
                support_count=len(negative),
                quotes=quotes,
            )
        ]

    def _extract_quote(self, answer: Answer, *, positive: bool) -> str:
        """Extract a quote from answer reasons or open-ended answers."""

        for item in answer.answers:
            reason = item.get("reason", "")
            if reason and isinstance(reason, str):
                return reason
        return "整体评价尚可" if positive else "仍需进一步观察"

    def _calc_persona_segments(self, answers: list[Answer]) -> PersonaSegments:
        """Determine most positive, negative, and highest-value persona IDs."""

        if not answers:
            return PersonaSegments(most_positive=[], most_negative=[], highest_value=[])
        scored = [(a.persona_id, a.overall_intent or 0) for a in answers]
        max_score = max(s for _, s in scored)
        min_score = min(s for _, s in scored)
        most_positive = [str(pid) for pid, s in scored if s == max_score]
        most_negative = [str(pid) for pid, s in scored if s == min_score]
        non_critical_high = [
            str(pid) for pid, s in scored if s == max_score
        ]
        return PersonaSegments(
            most_positive=most_positive,
            most_negative=most_negative,
            highest_value=non_critical_high,
        )

    def _generate_summary(
        self,
        answers: list[Answer],
        overall_intent: OverallIntentMetrics,
    ) -> str:
        """Generate a rule-based Chinese summary."""

        total = len(answers)
        avg = overall_intent.average
        if avg >= 4.0:
            tone = "偏积极"
        elif avg >= 3.0:
            tone = "中性"
        else:
            tone = "偏谨慎"
        return (
            f"本次共模拟 {total} 位角色完成测评，"
            f"平均购买意愿为 {avg} 分。"
            f"整体反馈{tone}。"
        )

    async def _build_qid_dim_map(self, survey_id: int | None) -> dict[str, str]:
        """Build a mapping from question ID to dimension."""

        if survey_id is None:
            return {}
        survey = await self.session.get(Survey, survey_id)
        if survey is None or not survey.questions:
            return {}
        return {str(q.get("id", "")): str(q.get("dim", "unknown")) for q in survey.questions}

    async def _load_personas(self, answers: list[Answer]) -> dict[int, Persona]:
        """Load all personas referenced by answers."""

        result: dict[int, Persona] = {}
        for answer in answers:
            if answer.persona_id not in result:
                persona = await self.personas.get_active_by_id(persona_id=answer.persona_id)
                if persona is not None:
                    result[answer.persona_id] = persona
        return result

    async def _to_response(self, report: Report, answers: list[Answer]) -> ReportResponse:
        """Convert a stored report to response schema."""

        metrics = ReportMetrics.model_validate(report.metrics) if report.metrics else ReportMetrics(
            overall_intent=OverallIntentMetrics(
                average=0.0,
                distribution=[IntentDistributionItem(score=s, count=0) for s in range(1, 6)],
                nps=0,
            ),
            dimensions_radar=[],
            price_sensitivity=PriceSensitivityMetrics(
                median_acceptable_price=0,
                distribution=[],
            ),
            segment_intent=[],
        )
        top_pros = [ProConItem.model_validate(p) for p in (report.top_pros or [])]
        top_cons = [ProConItem.model_validate(c) for c in (report.top_cons or [])]
        if report.persona_segments:
            persona_segments = PersonaSegments.model_validate(report.persona_segments)
        else:
            persona_segments = PersonaSegments(
                most_positive=[], most_negative=[], highest_value=[],
            )
        return self._build_response(report, metrics, top_pros, top_cons, persona_segments)

    def _build_response(
        self,
        report: Report,
        metrics: ReportMetrics,
        top_pros: list[ProConItem],
        top_cons: list[ProConItem],
        persona_segments: PersonaSegments,
    ) -> ReportResponse:
        """Build a ReportResponse from a report entity."""

        return ReportResponse(
            id=str(report.id),
            evaluation_id=str(report.evaluation_id),
            summary=report.summary or "",
            metrics=metrics,
            top_pros=top_pros,
            top_cons=top_cons,
            persona_segments=persona_segments,
            ai_disclaimer=AI_DISCLAIMER,
            generated_at=self._format_dt(report.created_at),
            pdf_url=report.pdf_url,
            share_token=report.share_token,
        )

    def _format_dt(self, value: datetime | None) -> str:
        """Format datetime to ISO 8601 with Z suffix."""

        if value is None:
            return datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
