from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse
from uuid import uuid4

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
from app.db.repositories.product import ProductRepository
from app.db.repositories.report import ReportRepository
from app.db.repositories.survey import SurveyRepository
from app.schemas.report import (
    BusinessConItem,
    BusinessDecisionSuggestion,
    BusinessEvidenceQuote,
    BusinessProItem,
    BusinessReportMetrics,
    BusinessReportResponse,
    BusinessTargetAudience,
    DeepAnalysisResponse,
    DeepAnalysisSectionItem,
    DeepInsightArticle,
    DeepInsightArticleParagraph,
    DeepInsightArticleSection,
    DeepInsightArticleSubsection,
    DeleteReportPdfsRequest,
    DimensionRadarItem,
    EvidenceChain,
    IntentDistributionItem,
    MarketingCopyAngle,
    OverallIntentMetrics,
    PersonaSegments,
    PriceSensitivityDistItem,
    PriceSensitivityMetrics,
    ProConItem,
    QuoteItem,
    ReportMetrics,
    ReportPdfListItem,
    ReportPdfListResponse,
    ReportPdfUploadResponse,
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
        self.products = ProductRepository(session)
        self.surveys = SurveyRepository(session)
        self.reports = ReportRepository(session)

    @staticmethod
    def _safe_pdf_filename(filename: str | None, fallback_title: str) -> str:
        """Return a readable, filesystem-safe PDF filename."""

        raw_name = (filename or "").strip()
        if raw_name.lower().endswith(".pdf"):
            raw_name = raw_name[:-4]
        title = raw_name or fallback_title or "CIBE产品数据白皮书"
        title = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", title)
        title = re.sub(r"\s+", "_", title).strip("._ ")
        title = title[:80].strip("._ ") or "CIBE产品数据白皮书"
        return f"{title}_{uuid4().hex[:8]}.pdf"

    @staticmethod
    def _pdf_title_from_url(pdf_url: str | None, fallback_title: str) -> str:
        """Return the readable title embedded in a saved PDF URL."""

        if not pdf_url:
            return fallback_title
        filename = Path(unquote(urlparse(pdf_url).path)).stem
        title = re.sub(r"_[0-9a-fA-F]{8}$", "", filename)
        title = re.sub(r"_\d{4}-\d{2}-\d{2}$", "", title)
        title = title.replace("_", " ").strip()
        if re.fullmatch(r"[A-Za-z0-9-]{24,}", title) or title.lower().startswith("evaluation "):
            return fallback_title
        return title or fallback_title

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

        qid_to_dim = await self._build_qid_dim_map(evaluation.survey_id)
        personas = await self._load_personas(answer_rows)

        overall_intent = self._calc_overall_intent(answer_rows)
        dimensions_radar = self._calc_dimensions_radar(answer_rows, qid_to_dim)
        price_sensitivity = self._calc_price_sensitivity(answer_rows, qid_to_dim)
        segment_intent = self._calc_segment_intent(answer_rows, personas)
        top_pros = self._calc_top_pros(answer_rows, personas)
        top_cons = self._calc_top_cons(answer_rows, personas)
        persona_segments = self._calc_persona_segments(answer_rows, personas)
        summary = self._generate_summary(answer_rows, overall_intent)

        metrics = ReportMetrics(
            overall_intent=overall_intent,
            dimensions_radar=dimensions_radar,
            price_sensitivity=price_sensitivity,
            segment_intent=segment_intent,
        )

        existing = await self.reports.get_by_evaluation_id(
            evaluation_id=evaluation.id,
            include_deleted=True,
        )
        if existing is not None:
            existing.deleted_at = None
            existing.summary = summary
            existing.metrics = metrics.model_dump()
            existing.top_pros = [p.model_dump() for p in top_pros]
            existing.top_cons = [c.model_dump() for c in top_cons]
            existing.persona_segments = persona_segments.model_dump()
            await self.session.commit()
            return self._build_response(
                existing,
                metrics,
                top_pros,
                top_cons,
                persona_segments,
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

    async def get_or_create_business_report(
        self,
        *,
        user: User,
        evaluation_id: int,
    ) -> BusinessReportResponse:
        """Return a business-shaped report using the stored report metrics."""

        report = await self.get_or_create_report(user=user, evaluation_id=evaluation_id)
        answer_rows = await self.answers.list_by_evaluation_id(
            evaluation_id=int(report.evaluation_id)
        )
        personas = await self._load_personas(answer_rows)

        product_name = ""
        evaluation = await self.evaluations.get_by_id_and_user_id(
            evaluation_id=evaluation_id,
            user_id=user.id,
        )
        if evaluation is not None and evaluation.product_id:
            product = await self.products.get_by_id_and_user_id(
                product_id=evaluation.product_id,
                user_id=user.id,
            )
            product_name = (product.name or "") if product else ""

        return self._to_business_response(report, answer_rows, personas, product_name)

    async def get_deep_analysis(
        self,
        *,
        user: User,
        evaluation_id: int,
    ) -> DeepAnalysisResponse:
        """Generate a deep-analysis narrative from existing business report data."""

        from app.ai.factory import get_ai_client
        from app.ai.json_utils import parse_json_response
        from app.ai.models import ModelRouter, TaskType

        report = await self.get_or_create_business_report(user=user, evaluation_id=evaluation_id)

        pros_text = "\n".join(
            f"- {p.title}（{p.support_count} 人支持）" for p in report.top_pros
        )
        cons_text = "\n".join(
            f"- {c.title}（{c.support_count} 人反对）" for c in report.top_cons
        )
        segments_text = "\n".join(
            f"- {seg.segment}：平均购买意愿 {seg.avg_intent:.1f}/5"
            for seg in report.metrics.persona_segments
        )

        user_prompt = (
            f"产品卖点优势：\n{pros_text}\n\n"
            f"产品卖点劣势：\n{cons_text}\n\n"
            f"消费者群体购买意愿：\n{segments_text}\n\n"
            "请按照系统指令格式输出 JSON。"
        )

        system_prompt = (
            "你是一位消费品市场研究分析师。根据调研数据，撰写以下三节深度分析报告，"
            "使用分析师语气，每节 100-200 字，有具体数字支撑，不出现 AI/虚拟/置信度 等字样，"
            "所有表述必须以消费群体为单位（如“学生党”“成分党”），禁止出现“X位消费者”等个体计数表达。\n\n"
            "严格按 JSON 输出，格式：\n"
            '{"sections": ['
            '{"title": "一、卖点与群体匹配", "content": "..."},'
            '{"title": "二、无人感兴趣的卖点", "content": "..."},'
            '{"title": "三、市场适配建议", "content": "..."}'
            "]}"
        )

        ai_client = get_ai_client()
        route = ModelRouter().get(TaskType.REPORT_SYNTHESIZE)
        raw = await ai_client.complete(
            system=system_prompt,
            user=user_prompt,
            endpoint_id=route.endpoint_id,
        )

        try:
            parsed = parse_json_response(raw)
            section_payload = parsed if isinstance(parsed, list) else parsed.get("sections", [])
            sections = [
                DeepAnalysisSectionItem(title=s["title"], content=s["content"])
                for s in section_payload
                if isinstance(s, dict) and s.get("title") and s.get("content")
            ]
            if not sections:
                sections = self._fallback_deep_analysis_sections(report)
        except Exception:
            sections = self._fallback_deep_analysis_sections(report)

        return DeepAnalysisResponse(
            sections=sections,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
        )

    def _fallback_deep_analysis_sections(
        self,
        report: BusinessReportResponse,
    ) -> list[DeepAnalysisSectionItem]:
        """Build deep-analysis sections from deterministic report data when AI JSON is invalid."""

        article = report.deep_insight_article
        if article and article.sections:
            sections: list[DeepAnalysisSectionItem] = []
            for section in article.sections:
                parts = [section.intro]
                for subsection in section.subsections:
                    paragraph_text = "；".join(
                        paragraph.body for paragraph in subsection.paragraphs if paragraph.body
                    )
                    if paragraph_text:
                        parts.append(f"{subsection.heading}：{paragraph_text}")
                sections.append(
                    DeepAnalysisSectionItem(
                        title=section.heading,
                        content="\n".join(part for part in parts if part),
                    )
                )
            return sections

        pros = "；".join(item.title for item in report.top_pros[:3]) or "机会点待继续验证"
        cons = "；".join(item.title for item in report.top_cons[:3]) or "风险点待继续验证"
        next_steps = "；".join(report.next_test_recommendations[:3]) or "继续补充下一轮验证。"
        return [
            DeepAnalysisSectionItem(
                title="一、卖点与群体匹配",
                content=f"本轮高频机会集中在：{pros}。这些判断来自调研角色标签所属群体的评分和原声证据。",
            ),
            DeepAnalysisSectionItem(
                title="二、无人感兴趣的卖点",
                content=f"当前主要阻力集中在：{cons}。后续应优先补充证据、价格解释或产品表达。",
            ),
            DeepAnalysisSectionItem(
                title="三、市场适配建议",
                content=next_steps,
            ),
        ]

    async def list_report_pdfs(self, *, user: User) -> ReportPdfListResponse:
        """Return generated PDF reports for the current user."""

        rows = await self.reports.list_pdfs_by_user_id(user_id=user.id)
        return ReportPdfListResponse(
            items=[
                ReportPdfListItem(
                    report_id=str(report.id),
                    evaluation_id=str(report.evaluation_id),
                    product_name=product_name,
                    pdf_title=self._pdf_title_from_url(report.pdf_url, product_name),
                    pdf_url=report.pdf_url or "",
                    generated_at=self._format_dt(report.updated_at or report.created_at),
                )
                for report, product_name in rows
            ]
        )

    async def delete_report_pdfs(
        self,
        *,
        user: User,
        payload: DeleteReportPdfsRequest,
    ) -> None:
        """Soft-delete generated PDF reports owned by the current user."""

        report_ids = [int(report_id) for report_id in payload.report_ids if report_id.isdigit()]
        reports = await self.reports.list_pdfs_by_ids_and_user_id(
            report_ids=report_ids,
            user_id=user.id,
        )
        for report in reports:
            await self.reports.soft_delete(report)
        await self.session.commit()

    async def save_report_pdf(
        self,
        *,
        user: User,
        evaluation_id: int,
        pdf_bytes: bytes,
        original_filename: str | None = None,
    ) -> ReportPdfUploadResponse:
        """Persist an exported PDF and attach its URL to the evaluation report."""

        if not pdf_bytes:
            raise AppException(
                code="REPORT_PDF_EMPTY",
                message="报告文件为空",
                http_status=status.HTTP_400_BAD_REQUEST,
                details={"evaluation_id": str(evaluation_id)},
            )
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
        report = await self.reports.get_by_evaluation_id(evaluation_id=evaluation.id)
        if report is None:
            await self.get_or_create_report(user=user, evaluation_id=evaluation.id)
            report = await self.reports.get_by_evaluation_id(evaluation_id=evaluation.id)
        if report is None:
            raise AppException(
                code="REPORT_NOT_FOUND",
                message="Report not found",
                http_status=status.HTTP_404_NOT_FOUND,
                details={"evaluation_id": str(evaluation_id)},
            )

        reports_dir = Path(__file__).parent.parent.parent / "static" / "reports" / str(user.id)
        reports_dir.mkdir(parents=True, exist_ok=True)
        product = await self.products.get_by_id_and_user_id(
            product_id=evaluation.product_id,
            user_id=user.id,
        )
        fallback_title = f"{product.name}_测品报告" if product and product.name else f"evaluation_{evaluation.id}_测品报告"
        filename = self._safe_pdf_filename(original_filename, fallback_title)
        (reports_dir / filename).write_bytes(pdf_bytes)
        report.pdf_url = f"/static/reports/{user.id}/{filename}"
        report.updated_at = datetime.now(UTC)
        await self.session.commit()
        return ReportPdfUploadResponse(
            report_id=str(report.id),
            evaluation_id=str(report.evaluation_id),
            pdf_url=report.pdf_url,
        )

    def _calc_overall_intent(self, answers: list[Answer]) -> OverallIntentMetrics:
        """Calculate purchase intent average and score distribution."""

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
        return OverallIntentMetrics(
            average=average,
            distribution=[IntentDistributionItem(score=s, count=dist[s]) for s in range(1, 6)],
            # NPS uses Bain's 0-10 recommendation question. This project records
            # 1-5 purchase intent, so we do not derive an NPS-like score here.
            nps=0,
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

    def _calc_price_sensitivity(
        self,
        answers: list[Answer],
        qid_to_dim: dict[str, str],
    ) -> PriceSensitivityMetrics:
        """Aggregate price mentions from real price-sensitivity answers."""

        prices: list[int] = []
        for answer in answers:
            answer_prices: list[int] = []
            for item in answer.answers:
                qid = str(item.get("qid", ""))
                dim = qid_to_dim.get(qid, "")
                text = self._item_text(item)
                if dim != "price_sensitivity" and not self._looks_like_price_text(text):
                    continue
                answer_prices.extend(self._extract_prices(text))
            if answer_prices:
                prices.append(answer_prices[0])

        if not prices:
            return PriceSensitivityMetrics(median_acceptable_price=0, distribution=[])

        prices.sort()
        mid = len(prices) // 2
        median = prices[mid] if len(prices) % 2 else round((prices[mid - 1] + prices[mid]) / 2)
        buckets = {
            "0-100": 0,
            "100-200": 0,
            "200-400": 0,
            "400+": 0,
        }
        for price in prices:
            if price < 100:
                buckets["0-100"] += 1
            elif price < 200:
                buckets["100-200"] += 1
            elif price < 400:
                buckets["200-400"] += 1
            else:
                buckets["400+"] += 1
        return PriceSensitivityMetrics(
            median_acceptable_price=median,
            distribution=[
                PriceSensitivityDistItem(range=label, count=count)
                for label, count in buckets.items()
                if count > 0
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

        return self._calc_theme_items(answers, personas, positive=True)

    def _calc_top_cons(
        self,
        answers: list[Answer],
        personas: dict[int, Persona],
    ) -> list[ProConItem]:
        """Extract top cons from critical/low-score answers."""

        return self._calc_theme_items(answers, personas, positive=False)

    def _calc_theme_items(
        self,
        answers: list[Answer],
        personas: dict[int, Persona],
        *,
        positive: bool,
    ) -> list[ProConItem]:
        themes = self._theme_definitions(positive=positive)
        theme_quotes: dict[str, list[QuoteItem]] = {title: [] for title, _ in themes}
        fallback_answers: list[Answer] = []

        for answer in answers:
            quote_text = self._extract_quote(answer, positive=positive)
            evidence_text = self._answer_evidence_text(answer, quote_text)
            matched = False
            for title, keywords in themes:
                if any(keyword in evidence_text for keyword in keywords):
                    theme_quotes[title].append(
                        QuoteItem(
                            persona_id=str(answer.persona_id),
                            persona_name=self._persona_group_label(personas.get(answer.persona_id)),
                            quote=quote_text,
                        )
                    )
                    matched = True
            if not matched:
                fallback_answers.append(answer)

        items = [
            ProConItem(
                title=title,
                support_count=len(quotes),
                quotes=quotes[:3],
            )
            for title, quotes in theme_quotes.items()
            if quotes
        ]
        items.sort(key=lambda item: item.support_count, reverse=True)
        if items:
            return items[:3]

        fallback = [
            answer
            for answer in fallback_answers
            if answer.overall_intent is not None
            and (
                (positive and answer.overall_intent >= 4)
                or (not positive and answer.overall_intent <= 3)
            )
        ]
        if not fallback:
            fallback = answers[:1] if positive else answers[-1:]
        quotes = [
            QuoteItem(
                persona_id=str(answer.persona_id),
                persona_name=self._persona_group_label(personas.get(answer.persona_id)),
                quote=self._extract_quote(answer, positive=positive),
            )
            for answer in fallback[:3]
        ]
        return [
            ProConItem(
                title=self._evidence_title(quotes, positive=positive),
                support_count=len(fallback),
                quotes=quotes,
            )
        ]

    def _theme_definitions(self, *, positive: bool) -> list[tuple[str, list[str]]]:
        if positive:
            return [
                ("品牌背书是主要正向信号", ["品牌", "大牌", "欧莱雅", "背书", "可信", "信任"]),
                ("温和修护是主要正向信号", ["温和", "修护", "敏感肌", "屏障"]),
                ("成分逻辑是主要正向信号", ["成分", "烟酰胺", "神经酰胺", "配方"]),
                ("价格匹配是主要正向信号", ["价格合理", "可以接受", "性价比", "划算"]),
                ("真实测评是主要正向信号", ["真实测评", "用户反馈", "实测", "评价"]),
            ]
        return [
            ("价格是主要决策顾虑", ["价格", "贵", "便宜", "预算", "不值"]),
            ("证据不足是主要决策顾虑", ["真实测评", "证据", "用户反馈", "检测", "功效证据"]),
            ("功效不确定是主要决策顾虑", ["功效", "效果", "有没有用", "担心没用"]),
            ("成分安全是主要决策顾虑", ["刺激", "过敏", "安全", "敏感"]),
        ]

    def _answer_evidence_text(self, answer: Answer, quote_text: str) -> str:
        parts = [quote_text, answer.summary_comment or ""]
        for item in answer.answers:
            parts.append(self._item_text(item))
        return " ".join(part for part in parts if part)

    def _extract_quote(self, answer: Answer, *, positive: bool) -> str:
        """Extract a quote from answer reasons or open-ended answers."""

        for item in answer.answers:
            reason = item.get("reason", "")
            if reason and isinstance(reason, str):
                return reason
        if answer.summary_comment:
            return answer.summary_comment
        return "整体评价尚可" if positive else "仍需进一步观察"

    def _looks_like_price_text(self, text: str) -> bool:
        """Return whether text likely contains price acceptance evidence."""

        return any(keyword in text for keyword in ["元", "价格", "价位", "预算", "贵", "便宜"])

    def _extract_prices(self, text: str) -> list[int]:
        """Extract plausible RMB prices from free-text answers."""

        prices: list[int] = []
        for match in re.finditer(r"(?<!\d)(\d{2,5})(?:\.\d+)?\s*(?:元|块|rmb|RMB)?", text):
            value = int(match.group(1))
            if 10 <= value <= 9999:
                prices.append(value)
        return prices

    def _item_text(self, item: dict[str, object]) -> str:
        answer = item.get("answer", "")
        if isinstance(answer, list):
            answer_text = " ".join(str(part) for part in answer)
        else:
            answer_text = str(answer)
        reason = item.get("reason", "")
        return f"{answer_text} {reason}".strip()

    def _evidence_title(self, quotes: list[QuoteItem], *, positive: bool) -> str:
        """Build a short conclusion title from actual evidence text."""

        all_text = " ".join(quote.quote for quote in quotes)
        keywords = [
            "温和修护",
            "敏感肌",
            "价格",
            "功效证据",
            "真实测评",
            "用户反馈",
            "成分",
            "使用体验",
            "性价比",
            "屏障修护",
        ]
        hits = [keyword for keyword in keywords if keyword in all_text]
        if hits:
            core = "、".join(hits[:2])
            suffix = "购买驱动" if positive else "决策顾虑"
            return f"{core}是主要{suffix}"
        if quotes:
            quote = self._shorten_sentence(quotes[0].quote, max_len=18)
            suffix = "正向信号" if positive else "风险信号"
            return f"{quote}是主要{suffix}"
        return "样本证据不足"

    def _shorten_sentence(self, text: str, *, max_len: int) -> str:
        cleaned = " ".join(text.replace("。", " ").replace("，", " ").split())
        return cleaned[:max_len]

    def _persona_group_label(self, persona: Persona | None) -> str:
        """Return a report-safe persona group label instead of a concrete name."""

        if persona is None:
            return "未分类消费者"
        if persona.persona_tag:
            return persona.persona_tag
        if persona.categories:
            category = str(persona.categories[0]).strip()
            if category:
                return f"{category}关注人群"
        if persona.city_tier:
            return f"{persona.city_tier}线城市消费者"
        return "未分类消费者"

    def _unique_labels(self, labels: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for label in labels:
            if label in seen:
                continue
            seen.add(label)
            result.append(label)
        return result

    def _calc_persona_segments(
        self,
        answers: list[Answer],
        personas: dict[int, Persona],
    ) -> PersonaSegments:
        """Determine most positive, negative, and highest-value persona groups."""

        if not answers:
            return PersonaSegments(most_positive=[], most_negative=[], highest_value=[])
        scored = [(a.persona_id, a.overall_intent or 0) for a in answers]
        max_score = max(s for _, s in scored)
        min_score = min(s for _, s in scored)
        most_positive = [
            self._persona_group_label(personas.get(pid))
            for pid, s in scored
            if s == max_score
        ]
        most_negative = [
            self._persona_group_label(personas.get(pid))
            for pid, s in scored
            if s == min_score
        ]
        non_critical_high = [
            self._persona_group_label(personas.get(pid))
            for pid, s in scored
            if s == max_score
        ]
        return PersonaSegments(
            most_positive=self._unique_labels(most_positive),
            most_negative=self._unique_labels(most_negative),
            highest_value=self._unique_labels(non_critical_high),
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
            f"本次共 {total} 位测品官完成调研，平均购买意愿为 {avg} 分，"
            f"整体反馈{tone}。报告结论基于角色实际回答、评分和原话证据生成。"
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

    def _to_business_response(
        self,
        report: ReportResponse,
        answers: list[Answer] | None = None,
        personas: dict[int, Persona] | None = None,
        product_name: str = "",
    ) -> BusinessReportResponse:
        """Map the base report contract to the mini-program business report contract."""

        distribution = {
            str(item.score): item.count
            for item in report.metrics.overall_intent.distribution
        }
        verdict = self._business_verdict(report.metrics.overall_intent.average)
        pro_items = [
            BusinessProItem(
                title=item.title,
                support_count=item.support_count,
                evidence_quotes=[
                    BusinessEvidenceQuote(
                        persona_name=quote.persona_name,
                        quote=quote.quote,
                    )
                    for quote in item.quotes
                ],
                business_implication=self._business_implication(item),
            )
            for item in report.top_pros
        ]
        con_items = [
            BusinessConItem(
                title=item.title,
                support_count=item.support_count,
                evidence_quotes=[
                    BusinessEvidenceQuote(
                        persona_name=quote.persona_name,
                        quote=quote.quote,
                    )
                    for quote in item.quotes
                ],
                improvement_suggestion=self._improvement_suggestion(item),
            )
            for item in report.top_cons
        ]
        likely_segments = [
            item.segment for item in report.metrics.segment_intent if item.avg_intent >= 4
        ]
        unlikely_segments = [
            item.segment for item in report.metrics.segment_intent if item.avg_intent < 4
        ]
        if not likely_segments:
            likely_segments = report.persona_segments.highest_value
        if not unlikely_segments:
            unlikely_segments = report.persona_segments.most_negative
        top_quote_sources = [
            quote
            for item in report.top_pros
            for quote in item.quotes
        ][:3]
        evidence_quotes = [
            BusinessEvidenceQuote(persona_name=quote.persona_name, quote=quote.quote)
            for quote in top_quote_sources
        ]
        marketing_angles = [
            MarketingCopyAngle(
                angle=item.title,
                suitable_segment=item.quotes[0].persona_name if item.quotes else "待验证人群",
                risk_note="只使用本次调研已被原话支持的表达，避免扩大功效承诺。",
            )
            for item in report.top_pros[:3]
        ]
        next_recs = self._next_test_recommendations(report)
        deep_article = self._build_deep_insight_article(
            report=report,
            marketing_angles=marketing_angles,
            next_recs=next_recs,
            product_name=product_name,
        )

        return BusinessReportResponse(
            id=report.id,
            evaluation_id=report.evaluation_id,
            template_key="business_report_v1",
            ai_disclaimer=report.ai_disclaimer,
            executive_summary=[
                report.summary,
                self._intent_summary(report),
                self._price_summary(report.metrics.price_sensitivity),
            ],
            decision_suggestion=BusinessDecisionSuggestion(
                verdict=verdict,
                reason=self._business_reason(verdict),
                confidence=self._confidence(report),
            ),
            metrics=BusinessReportMetrics(
                overall_intent_avg=report.metrics.overall_intent.average,
                nps=report.metrics.overall_intent.nps,
                intent_distribution=distribution,
                dimension_scores=report.metrics.dimensions_radar,
                price_sensitivity=report.metrics.price_sensitivity.distribution,
                persona_segments=report.metrics.segment_intent,
            ),
            top_pros=pro_items,
            top_cons=con_items,
            target_audience=BusinessTargetAudience(
                most_likely_to_buy=likely_segments,
                least_likely_to_buy=unlikely_segments,
                channel_recommendation=self._channel_recommendations(
                    report,
                    answers or [],
                    personas or {},
                ),
            ),
            marketing_copy_angles=marketing_angles,
            evidence_chains=[
                EvidenceChain(
                    evidence_type="opportunity",
                    conclusion=report.top_pros[0].title if report.top_pros else report.summary,
                    support_count=report.top_pros[0].support_count if report.top_pros else 0,
                    source_roles=[quote.persona_name for quote in top_quote_sources],
                    source_answers=evidence_quotes,
                    business_action=(
                        "把被多类角色标签所属群体支持的卖点转化为下一轮产品页文案或概念测试变量。"
                    ),
                )
            ],
            next_test_recommendations=next_recs,
            generated_at=report.generated_at,
            deep_insight_article=deep_article,
        )

    def _business_verdict(self, average_intent: float) -> str:
        if average_intent >= 4.0:
            return "go"
        if average_intent >= 3.0:
            return "iterate"
        return "pause"

    def _business_reason(self, verdict: str) -> str:
        if verdict == "go":
            return "购买意愿信号较强，可以在控制风险的前提下继续推进。"
        if verdict == "iterate":
            return "购买意愿存在分化，建议先围绕主要顾虑迭代后再放大投放。"
        return "购买意愿偏弱，建议暂停放量，优先重构卖点、价格或证据表达。"

    def _business_implication(self, item: ProConItem) -> str:
        quote = item.quotes[0].quote if item.quotes else item.title
        return (
            f"{self._persona_group_summary(item, '支持这一信号')}"
            f"可优先把“{item.title}”用于产品页首屏、短视频开场或私域种草话术，"
            f"并保留原话依据：{quote}"
        )

    def _improvement_suggestion(self, item: ProConItem) -> str:
        quote = item.quotes[0].quote if item.quotes else item.title
        return (
            f"{self._persona_group_summary(item, '暴露该风险')}"
            f"下一轮应针对“{item.title}”补充证据、价格解释或真实测评内容；"
            f"典型原话是：{quote}"
        )

    def _persona_group_summary(self, item: ProConItem, action: str) -> str:
        labels = self._unique_labels([quote.persona_name for quote in item.quotes])
        if not labels:
            return f"{item.support_count}类角色标签所属群体{action}。"
        if len(labels) == 1:
            return f"{labels[0]}这一类角色标签所属群体{action}。"
        visible_labels = labels[:3]
        connector = "等" if len(labels) > len(visible_labels) else "这"
        return (
            f"{'、'.join(visible_labels)}{connector}{len(labels)}类角色标签所属群体"
            f"{action}。"
        )

    def _intent_summary(self, report: ReportResponse) -> str:
        avg = report.metrics.overall_intent.average
        distribution = report.metrics.overall_intent.distribution
        total = sum(item.count for item in distribution)
        top_box = sum(item.count for item in distribution if item.score == 5)
        top2_box = sum(item.count for item in distribution if item.score >= 4)
        bottom2_box = sum(item.count for item in distribution if item.score <= 2)
        top_box_pct = round(top_box / total * 100) if total else 0
        top2_box_pct = round(top2_box / total * 100) if total else 0
        bottom2_box_pct = round(bottom2_box / total * 100) if total else 0
        return (
            f"购买意愿均分 {avg}/5；最高档占比（5分）{top_box_pct}%，"
            f"高意向占比（4-5分）{top2_box_pct}%，"
            f"低意向占比（1-2分）{bottom2_box_pct}%；样本数 {total}。"
        )

    def _price_summary(self, metrics: PriceSensitivityMetrics) -> str:
        if not metrics.distribution:
            return "本次回答没有足够明确的价格数字，价格敏感度需要在下一轮调研中补题验证。"
        ranges = "、".join(f"{item.range}：{item.count}人次" for item in metrics.distribution)
        return f"价格回答中位数约 {metrics.median_acceptable_price} 元，分布为 {ranges}。"

    def _confidence(self, report: ReportResponse) -> float:
        total = sum(item.count for item in report.metrics.overall_intent.distribution)
        evidence_count = sum(item.support_count for item in report.top_pros + report.top_cons)
        base = min(0.85, 0.45 + total * 0.06 + evidence_count * 0.02)
        if not report.metrics.price_sensitivity.distribution:
            base -= 0.08
        return round(max(0.35, min(0.9, base)), 2)

    def _channel_recommendations(
        self,
        report: ReportResponse,
        answers: list[Answer],
        personas: dict[int, Persona],
    ) -> list[str]:
        high_intent_answers = [
            answer
            for answer in answers
            if answer.overall_intent is not None and answer.overall_intent >= 4
        ]
        if not high_intent_answers:
            high_intent_answers = [
                answer
                for answer in answers
                if answer.overall_intent is not None and answer.overall_intent >= 3
            ]

        channel_counts: Counter[str] = Counter()
        channel_segments: dict[str, set[str]] = defaultdict(set)
        for answer in high_intent_answers:
            persona = personas.get(answer.persona_id)
            if persona is None:
                continue
            segment = self._persona_group_label(persona)
            for channel in self._persona_info_channels(persona):
                channel_counts[channel] += 1
                channel_segments[channel].add(segment)

        if not channel_counts:
            return ["本轮未形成明确渠道证据，建议下一轮补充触达渠道问题。"]

        top_channels = [
            channel
            for channel, _count in channel_counts.most_common(3)
        ]
        top_segments = self._unique_labels(
            segment
            for channel in top_channels
            for segment in sorted(channel_segments[channel])
        )[:3]
        recommendations = [
            (
                f"优先在{'、'.join(top_channels)}触达"
                f"{'、'.join(top_segments) if top_segments else '高意向群体'}。"
            )
        ]
        if report.top_pros:
            recommendations.append(
                f"围绕“{report.top_pros[0].title}”制作渠道素材，保留受访群体原声。"
            )
        if report.top_cons:
            recommendations.append(f"针对“{report.top_cons[0].title}”补充证据后再投放。")
        return recommendations[:3]

    def _persona_info_channels(self, persona: Persona) -> list[str]:
        profile = persona.profile if isinstance(persona.profile, dict) else {}
        raw_channels = profile.get("info_channels", [])
        if isinstance(raw_channels, str):
            raw_channels = re.split(r"[、,，/;；\s]+", raw_channels)
        if not isinstance(raw_channels, list):
            return []
        channels = [
            str(channel).strip()
            for channel in raw_channels
            if str(channel).strip()
        ]
        return self._unique_labels(channels)

    def _next_test_recommendations(self, report: ReportResponse) -> list[str]:
        recommendations: list[str] = []
        if report.top_pros:
            recommendations.append(f"围绕“{report.top_pros[0].title}”做 A/B 文案测试。")
        if report.top_cons:
            recommendations.append(f"针对“{report.top_cons[0].title}”补充证据或改进产品表达。")
        if report.metrics.price_sensitivity.distribution:
            recommendations.append("按高意向人群复测价格带，确认可接受价格上限。")
        else:
            recommendations.append("下一轮加入明确价格题，避免价格结论缺证据。")
        return recommendations[:3]

    # ------------------------------------------------------------------ #
    #  Deep-insight article builder                                        #
    # ------------------------------------------------------------------ #

    _ORDINALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]

    def _build_deep_insight_article(
        self,
        report: ReportResponse,
        marketing_angles: list[MarketingCopyAngle],
        next_recs: list[str],
        product_name: str,
    ) -> DeepInsightArticle:
        """Build a formal article-style deep-insight block from existing report data."""

        n_segs = len(report.metrics.segment_intent)
        seg_label = f"{n_segs}类受众群体" if n_segs > 0 else "全部受众群体"
        name = product_name or "本次测品产品"
        short_name = name[:10]

        title = f"「{short_name}」卖点穿透力与市场适配深度洞察"
        abstract = (
            f"本报告对{short_name}在{seg_label}中的反映样本进行深度拆解，"
            "聚焦回答三个具有决策意义的问题：哪些卖点完成了对特定人群的精准锚定、"
            "哪些卖点在所有群体面前丧失了说服力、产品下一步应如何调整方能切入真实市场。"
        )

        section1 = self._build_section_angles(marketing_angles, report)
        section2 = self._build_section_cold_points(report)
        section3 = self._build_section_market_fit(next_recs)

        return DeepInsightArticle(
            title=title,
            abstract=abstract,
            sections=[section1, section2, section3],
        )

    def _build_section_angles(
        self,
        angles: list[MarketingCopyAngle],
        report: ReportResponse,
    ) -> DeepInsightArticleSection:
        """Chapter 1: selling-point × audience fit."""

        subsections: list[DeepInsightArticleSubsection] = []
        for i, angle in enumerate(angles[:4]):
            ordinal = self._ORDINALS[i] if i < len(self._ORDINALS) else str(i + 1)
            subsections.append(
                DeepInsightArticleSubsection(
                    heading=f"（{ordinal}）「{angle.angle}」——{angle.suitable_segment}的核心响应点",
                    paragraphs=[
                        DeepInsightArticleParagraph(
                            label="人群锁定",
                            body=(
                                f"{angle.suitable_segment}是该卖点的核心响应群体，"
                                "在本轮反映样本中该群体对这一表达的接受度明显优于整体均值。"
                            ),
                        ),
                        DeepInsightArticleParagraph(
                            label="共鸣触点",
                            body=self._resonance_body(angle, report),
                        ),
                        DeepInsightArticleParagraph(
                            label="边界提示",
                            body=(
                                angle.risk_note
                                if angle.risk_note
                                else (
                                    "该卖点在非核心受众中的拉力有限，"
                                    "投放时应控制覆盖范围，避免将预算分散至低共鸣群体。"
                                )
                            ),
                        ),
                    ],
                )
            )

        if not subsections:
            subsections.append(
                DeepInsightArticleSubsection(
                    heading="（一）卖点数据待积累",
                    paragraphs=[
                        DeepInsightArticleParagraph(
                            label="",
                            body="本轮暂未形成足够的卖点x人群交叉数据，建议在下一轮调研中补充相关维度问题。",
                        )
                    ],
                )
            )

        return DeepInsightArticleSection(
            heading="一、卖点穿透力的人群锁定",
            intro=(
                "卖点的价值不由自身决定，而由其能否在特定人群心智中完成精准锚定来决定。"
                "本节按受众群体的反映强度，对各核心卖点逐一进行穿透力归因。"
            ),
            subsections=subsections,
        )

    def _build_section_cold_points(self, report: ReportResponse) -> DeepInsightArticleSection:
        """Chapter 2: selling points that failed to resonate with any segment."""

        cons = report.top_cons[:2]
        if cons:
            cold_titles = "、".join(f"「{c.title}」" for c in cons)
            phenomenon = (
                f"本轮调研中，{cold_titles}在覆盖的全部受众群体中均未形成明显的正向拉力，"
                "相关反映样本中的支持信号偏弱，未见跨群体的一致性认可。"
            )
            attribution = self._cold_attribution(cons)
        else:
            phenomenon = (
                "本轮调研中所有核心卖点均获得了不同程度的群体响应，"
                "未发现全面冷场的卖点，产品整体表达与受众需求的匹配度尚可。"
            )
            attribution = (
                "当前卖点矩阵的群体覆盖较为均衡，建议在下一轮调研中进一步测试卖点之间的优先级，"
                "找出最具杠杆效应的核心表达。"
            )

        return DeepInsightArticleSection(
            heading="二、转化无力的卖点诊断",
            intro=(
                "并非所有卖点都能形成购买驱动力。"
                "本节聚焦在本轮调研中未能产生群体性共鸣的卖点，"
                "进行归因诊断后给出处置方案，避免营销预算消耗在无效信息上。"
            ),
            subsections=[
                DeepInsightArticleSubsection(
                    heading="（一）现象描述",
                    paragraphs=[DeepInsightArticleParagraph(label="", body=phenomenon)],
                ),
                DeepInsightArticleSubsection(
                    heading="（二）归因分析",
                    paragraphs=[DeepInsightArticleParagraph(label="", body=attribution)],
                ),
                DeepInsightArticleSubsection(
                    heading="（三）处置建议",
                    paragraphs=[
                        DeepInsightArticleParagraph(
                            label="",
                            body=(
                                "建议将上述卖点从产品首屏与投放素材的核心位置移除，"
                                "转入长效心智培育层，仅在私域复购场景与高客单产品线中保留呈现。"
                                "该类卖点并非产品劣势，而是在当前受众群体结构下缺乏即时转化驱动力，"
                                "可在细分渠道做定向小量测试后再行判断。"
                            ),
                        )
                    ],
                ),
            ],
        )

    def _build_section_market_fit(self, next_recs: list[str]) -> DeepInsightArticleSection:
        """Chapter 3: actionable market-adaptation paths."""

        subsections: list[DeepInsightArticleSubsection] = []
        for i, rec in enumerate(next_recs[:4]):
            ordinal = self._ORDINALS[i] if i < len(self._ORDINALS) else str(i + 1)
            subsections.append(
                DeepInsightArticleSubsection(
                    heading=f"（{ordinal}）{self._rec_label(rec, i)}",
                    paragraphs=[DeepInsightArticleParagraph(label="", body=rec)],
                )
            )

        if not subsections:
            subsections.append(
                DeepInsightArticleSubsection(
                    heading="（一）持续验证与迭代",
                    paragraphs=[
                        DeepInsightArticleParagraph(
                            label="",
                            body=(
                                "建议在下一轮调研中针对卖点表达、价格锚点和目标渠道进行专项验证，"
                                "以数据替代经验判断，稳步缩小市场适配缺口。"
                            ),
                        )
                    ],
                )
            )

        return DeepInsightArticleSection(
            heading="三、市场适配的落地路径",
            intro=(
                "调研结论的最终价值在于转化为可执行动作。"
                "基于卖点穿透力与冷场诊断的双重判断，本节给出可即时落地的适配路径。"
            ),
            subsections=subsections,
        )

    def _resonance_body(self, angle: MarketingCopyAngle, report: ReportResponse) -> str:
        """Build the 共鸣触点 paragraph for one angle."""

        matching_pro = next(
            (p for p in report.top_pros if p.title == angle.angle),
            None,
        )
        if matching_pro and matching_pro.quotes:
            quote = matching_pro.quotes[0].quote
            return (
                f"「{angle.angle}」这一特性在{angle.suitable_segment}的消费决策链路中扮演"
                f"核心说服角色。典型反映原话：{quote}"
            )
        return (
            f"「{angle.angle}」与{angle.suitable_segment}的既有认知或使用场景高度同频，"
            "该群体在调研中对相关表达呈现出明显高于均值的正向接受度。"
        )

    def _cold_attribution(self, cons: list[ProConItem]) -> str:
        """Build the 归因分析 paragraph for cold/weak selling points."""

        titles = "、".join(f"「{c.title}」" for c in cons)
        quote_hints: list[str] = []
        for con in cons:
            if con.quotes:
                quote_hints.append(con.quotes[0].quote)
        if quote_hints:
            hint = quote_hints[0]
            return (
                f"{titles}属于在本轮受众结构下缺乏即时功效触点或情绪共鸣的表达类型。"
                f"典型反映原话印证了这一判断：{hint}。"
                "建议在重新包装表达逻辑之前，先确认该卖点是否对应了受众真实存在的决策障碍。"
            )
        return (
            f"{titles}属于在本轮受众结构下缺乏即时功效触点或情绪共鸣的表达类型，"
            "难以在购买决策的关键路径上形成锚点。"
            "建议优先评估其必要性，或重新包装为更贴近受众场景语言的表述方式。"
        )

    _REC_LABEL_KEYWORDS: list[tuple[str, str]] = [
        ("A/B", "卖点 A/B 文案测试"),
        ("价格", "价格带验证与定价锚点"),
        ("渠道", "渠道布局与触点优化"),
        ("证据", "证据补充与信任建立"),
        ("改进", "产品表达迭代"),
        ("复测", "复测命题设计"),
        ("人群", "目标人群精细化"),
        ("投放", "投放策略调整"),
    ]
    _REC_FALLBACK_LABELS = ["卖点深化", "渠道重组", "证据补充", "迭代复测"]

    def _rec_label(self, rec: str, index: int) -> str:
        """Derive a short heading label from a recommendation sentence."""

        for keyword, label in self._REC_LABEL_KEYWORDS:
            if keyword in rec:
                return label
        return self._REC_FALLBACK_LABELS[index % len(self._REC_FALLBACK_LABELS)]

    def _format_dt(self, value: datetime | None) -> str:
        """Format datetime to ISO 8601 with Z suffix."""

        if value is None:
            return datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
