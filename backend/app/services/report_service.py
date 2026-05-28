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

# 问卷维度英文 → 中文标签映射（与 survey generator 的 10 维度对齐）
DIM_LABEL_MAP: dict[str, str] = {
    "first_impression": "第一印象",
    "purchase_motivation": "购买动机",
    "price_sensitivity": "价格敏感度",
    "package_appearance": "包装外观",
    "competitor_comparison": "竞品对比",
    "usage_scenario": "使用场景",
    "repurchase_intent": "复购意愿",
    "nps_recommendation": "推荐意愿",
    "channel_touchpoint": "渠道触点",
    "painpoint_improvement": "痛点改进",
}

# 维度 → 改进建议映射
DIM_IMPROVEMENT_MAP: dict[str, str] = {
    "first_impression": "优化产品主图和一句话卖点，提升 3 秒吸引力",
    "purchase_motivation": "强化核心卖点与目标人群痛点的匹配度",
    "price_sensitivity": "调整定价策略或增加赠品提升性价比感知",
    "package_appearance": "优化包装设计使其更贴合目标人群审美偏好",
    "competitor_comparison": "突出差异化优势，补齐竞品已有的关键功能",
    "usage_scenario": "丰富使用场景展示，降低用户想象门槛",
    "repurchase_intent": "强化使用效果反馈，建立长期复购动机",
    "nps_recommendation": "提升社交分享价值，降低推荐心理门槛",
    "channel_touchpoint": "优化渠道布局，在目标人群高频触点增加曝光",
    "painpoint_improvement": "针对用户反馈的痛点进行产品迭代改进",
}


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
        price_sensitivity = self._calc_price_sensitivity(answer_rows)
        segment_intent = self._calc_segment_intent(answer_rows, personas)
        top_pros = self._calc_top_pros(answer_rows, personas, qid_to_dim)
        top_cons = self._calc_top_cons(answer_rows, personas, qid_to_dim)
        persona_segments = self._calc_persona_segments(answer_rows)
        summary = self._generate_summary(answer_rows, overall_intent, dimensions_radar)

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

    def _calc_price_sensitivity(self, answers: list[Answer]) -> PriceSensitivityMetrics:
        """从答卷中提取价格敏感度数据。"""

        prices: list[float] = []
        for answer in answers:
            for item in answer.answers:
                if item.get("type") != "price_open":
                    continue
                val = item.get("answer")
                if isinstance(val, (int, float)) and val > 0:
                    prices.append(float(val))

        if not prices:
            return PriceSensitivityMetrics(
                median_acceptable_price=0,
                distribution=[],
            )

        prices.sort()
        n = len(prices)
        median = prices[n // 2] if n % 2 == 1 else (prices[n // 2 - 1] + prices[n // 2]) / 2

        # 动态分桶
        bins = [(0, 100), (100, 200), (200, 400), (400, float("inf"))]
        dist: list[PriceSensitivityDistItem] = []
        for low, high in bins:
            count = sum(1 for p in prices if low <= p < high)
            if count > 0:
                label = f"{low}-{int(high)}" if high != float("inf") else f"{low}+"
                dist.append(PriceSensitivityDistItem(range=label, count=count))

        return PriceSensitivityMetrics(
            median_acceptable_price=round(median),
            distribution=dist,
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
        qid_to_dim: dict[str, str],
    ) -> list[ProConItem]:
        """按维度分组提取亮点，取平均分最高的维度。"""

        return self._build_procon_by_dimension(
            answers, personas, qid_to_dim, positive=True,
        )

    def _calc_top_cons(
        self,
        answers: list[Answer],
        personas: dict[int, Persona],
        qid_to_dim: dict[str, str],
    ) -> list[ProConItem]:
        """按维度分组提取风险，取平均分最低的维度。"""

        return self._build_procon_by_dimension(
            answers, personas, qid_to_dim, positive=False,
        )

    def _build_procon_by_dimension(
        self,
        answers: list[Answer],
        personas: dict[int, Persona],
        qid_to_dim: dict[str, str],
        *,
        positive: bool,
    ) -> list[ProConItem]:
        """按维度聚合 scale_1_5 得分，生成 ProConItem 列表。

        positive=True → 取得分最高的 3 个维度作为亮点
        positive=False → 取得分最低的 3 个维度作为风险
        """

        # 1. 按维度收集 (persona_id, score, reason)
        dim_data: dict[str, list[tuple[int, float, str]]] = defaultdict(list)
        for answer in answers:
            for item in answer.answers:
                if item.get("type") != "scale_1_5":
                    continue
                qid = str(item.get("qid", ""))
                dim = qid_to_dim.get(qid, "")
                if not dim:
                    continue
                val = item.get("answer")
                reason = item.get("reason", "") or ""
                if isinstance(val, (int, float)):
                    dim_data[dim].append((answer.persona_id, float(val), reason))

        # 2. 计算每个维度的平均分并排序
        dim_avg: list[tuple[str, float, list[tuple[int, float, str]]]] = []
        for dim, entries in dim_data.items():
            avg = sum(e[1] for e in entries) / len(entries) if entries else 0.0
            dim_avg.append((dim, avg, entries))

        dim_avg.sort(key=lambda x: x[1], reverse=positive)

        # 3. 取 top 3 维度生成 ProConItem
        results: list[ProConItem] = []
        for dim, avg_score, entries in dim_avg[:3]:
            # 按分数排序选代表性引用
            if positive:
                sorted_entries = sorted(entries, key=lambda e: e[1], reverse=True)
            else:
                sorted_entries = sorted(entries, key=lambda e: e[1])

            raw_quotes: list[tuple[str, str, str]] = []
            quotes: list[QuoteItem] = []
            for pid, score, reason in sorted_entries[:3]:
                persona = personas.get(pid)
                name = persona.name if persona else "未知"
                text = reason if reason else ("整体评价尚可" if positive else "仍需进一步观察")
                raw_quotes.append((str(pid), name, text))
                quotes.append(QuoteItem(persona_id=str(pid), persona_name=name, quote=text))

            title = self._extract_title_from_dim(dim, raw_quotes, positive=positive)
            # 风险项追加改进建议
            if not positive:
                suggestion = DIM_IMPROVEMENT_MAP.get(dim, "")
                if suggestion:
                    title = f"{title}——{suggestion}"

            results.append(
                ProConItem(
                    title=title,
                    support_count=len(entries),
                    quotes=quotes,
                )
            )

        # 兜底：如果没有维度数据，给出默认项
        if not results:
            fallback_quotes: list[QuoteItem] = []
            for answer in answers[:1]:
                persona = personas.get(answer.persona_id)
                name = persona.name if persona else "未知"
                fallback_quotes.append(
                    QuoteItem(
                        persona_id=str(answer.persona_id),
                        persona_name=name,
                        quote="整体评价尚可" if positive else "仍需进一步观察",
                    )
                )
            results.append(
                ProConItem(
                    title="产品整体获得正面评价" if positive else "部分角色对产品持保留态度",
                    support_count=len(answers),
                    quotes=fallback_quotes,
                )
            )

        return results

    def _extract_quote(self, answer: Answer, *, positive: bool) -> str:
        """Extract a quote from answer reasons or open-ended answers."""

        for item in answer.answers:
            reason = item.get("reason", "")
            if reason and isinstance(reason, str):
                return reason
        return "整体评价尚可" if positive else "仍需进一步观察"

    @staticmethod
    def _extract_title_from_dim(
        dim: str,
        quotes: list[tuple[str, str, str]],
        *,
        positive: bool,
    ) -> str:
        """根据维度和代表性引用生成 pro/con 标题。

        Args:
            dim: 维度英文 key（如 "first_impression"）
            quotes: [(persona_id, persona_name, quote_text), ...]
            positive: True=亮点, False=风险
        """
        dim_label = DIM_LABEL_MAP.get(dim, dim)
        if not quotes:
            return f"{dim_label}{'表现突出' if positive else '有待提升'}"
        # 取最长引用作为摘要片段
        best_quote = max(quotes, key=lambda q: len(q[2]))[2]
        snippet = best_quote[:20].rstrip("，。、！？…")
        if len(best_quote) > 20:
            snippet += "…"
        return f"{dim_label}：{snippet}"

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
        dimensions_radar: list[DimensionRadarItem] | None = None,
    ) -> str:
        """Generate a rule-based Chinese summary with dimension insights."""

        total = len(answers)
        avg = overall_intent.average
        if avg >= 4.0:
            tone = "偏积极"
        elif avg >= 3.0:
            tone = "中性"
        else:
            tone = "偏谨慎"

        parts: list[str] = [
            f"本次共模拟 {total} 位角色完成测评，",
            f"平均购买意愿为 {avg} 分。",
            f"整体反馈{tone}。",
        ]

        if dimensions_radar:
            sorted_dims = sorted(dimensions_radar, key=lambda d: d.score, reverse=True)
            best = sorted_dims[0]
            worst = sorted_dims[-1]
            best_label = DIM_LABEL_MAP.get(best.dim, best.dim)
            worst_label = DIM_LABEL_MAP.get(worst.dim, worst.dim)
            parts.append(
                f"维度亮点：{best_label}（{best.score}分）；"
                f"短板：{worst_label}（{worst.score}分）。"
            )

        return "".join(parts)

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
