from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.db.models.product import Product
from app.db.models.user import User
from app.db.models.whitepaper import Whitepaper
from app.db.repositories.evaluation import EvaluationRepository
from app.db.repositories.whitepaper import WhitepaperRepository
from app.schemas.whitepaper import WhitepaperResponse

# Estimated total seconds for a full whitepaper generation run.
_PROGRESS_TOTAL_SECONDS = 180.0
_CHART_BLOCK_START = "<!-- REAL_METRIC_CHARTS_START -->"
_CHART_BLOCK_END = "<!-- REAL_METRIC_CHARTS_END -->"

logger = logging.getLogger(__name__)


def _short_product_name(name: str | None) -> str:
    """Return the display/generation product name used by mini-program reports."""

    value = (name or "").strip()
    return value[:10] or "未命名产品"


class WhitepaperService:
    """Trigger and persist CIBE-style whitepapers backed by the external proxy."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.evaluations = EvaluationRepository(session)
        self.whitepapers = WhitepaperRepository(session)
        self._settings = get_settings()

    async def request_generation(
        self,
        *,
        user: User,
        evaluation_id: int,
        product_name: str,
        product_description: str | None,
    ) -> WhitepaperResponse:
        """Ensure a whitepaper row exists and trigger background generation if needed."""

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

        existing = await self.whitepapers.get_by_evaluation_id(evaluation_id=evaluation_id)
        if existing is None:
            product_description = await self._build_report_enriched_description(
                user=user,
                evaluation_id=evaluation_id,
                product_description=product_description,
            )
            existing = await self.whitepapers.create(
                {
                    "evaluation_id": evaluation_id,
                    "product_name": _short_product_name(product_name),
                    "product_description": product_description,
                    "status": "generating",
                }
            )
            await self.session.commit()
            asyncio.create_task(
                self._generate_in_background(
                    whitepaper_id=existing.id,
                    product_name=existing.product_name,
                    product_description=existing.product_description,
                )
            )
        elif existing.status == "failed":
            existing.status = "generating"
            existing.error_message = None
            existing.product_name = _short_product_name(product_name or existing.product_name)
            existing.product_description = await self._build_report_enriched_description(
                user=user,
                evaluation_id=evaluation_id,
                product_description=product_description or existing.product_description,
            )
            await self.session.commit()
            asyncio.create_task(
                self._generate_in_background(
                    whitepaper_id=existing.id,
                    product_name=existing.product_name,
                    product_description=existing.product_description,
                )
            )
        elif existing.status == "ready":
            existing.product_description = await self._build_report_enriched_description(
                user=user,
                evaluation_id=evaluation_id,
                product_description=product_description or existing.product_description,
            )
            if existing.markdown:
                existing.markdown = self._append_real_metric_charts(
                    markdown=existing.markdown,
                    source_text=existing.product_description or "",
                )
            await self.session.commit()

        return self._to_response(existing)

    async def get_by_evaluation(
        self,
        *,
        user: User | None,
        evaluation_id: int,
    ) -> WhitepaperResponse:
        """Fetch the whitepaper for an evaluation.

        When *user* is provided ownership is verified.  When None (public /
        unauthenticated access) the lookup is done by evaluation_id alone so
        that share links work without a JWT.
        """

        if user is not None:
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
        else:
            # Public access — fetch evaluation without user scope
            from sqlalchemy import select
            from app.db.models.evaluation import Evaluation

            result = await self.session.execute(
                select(Evaluation).where(Evaluation.id == evaluation_id)
            )
            evaluation = result.scalar_one_or_none()
            if evaluation is None:
                raise AppException(
                    code="EVALUATION_NOT_FOUND",
                    message="Evaluation not found",
                    http_status=status.HTTP_404_NOT_FOUND,
                    details={"evaluation_id": str(evaluation_id)},
                )

        whitepaper = await self.whitepapers.get_by_evaluation_id(evaluation_id=evaluation_id)
        if whitepaper is None:
            # Auto-create the row + kick off background generation using the
            # evaluation's product so the report page can poll progress immediately.
            product = await self.session.get(Product, evaluation.product_id)
            product_name = _short_product_name(product.name if product else None)
            owner_user = user or await self.session.get(User, evaluation.user_id)
            product_description = await self._build_report_enriched_description(
                user=owner_user,
                evaluation_id=evaluation_id,
                product_description=(product.description if product else None),
            )
            whitepaper = await self.whitepapers.create(
                {
                    "evaluation_id": evaluation_id,
                    "product_name": product_name,
                    "product_description": product_description,
                    "status": "generating",
                }
            )
            await self.session.commit()
            asyncio.create_task(
                self._generate_in_background(
                    whitepaper_id=whitepaper.id,
                    product_name=whitepaper.product_name,
                    product_description=whitepaper.product_description,
                )
            )
        elif whitepaper.status == "ready":
            owner_user = user or await self.session.get(User, evaluation.user_id)
            whitepaper.product_description = await self._build_report_enriched_description(
                user=owner_user,
                evaluation_id=evaluation_id,
                product_description=whitepaper.product_description,
            )
            if whitepaper.markdown:
                whitepaper.markdown = self._append_real_metric_charts(
                    markdown=whitepaper.markdown,
                    source_text=whitepaper.product_description or "",
                )
            await self.session.commit()
        return self._to_response(whitepaper)

    async def _generate_in_background(
        self,
        *,
        whitepaper_id: int,
        product_name: str,
        product_description: str | None,
    ) -> None:
        """Run the external whitepaper call without blocking the caller."""

        from app.db.session import AsyncSessionFactory  # local import to avoid cycles

        text_payload = self._build_input_text(product_name, product_description)
        try:
            markdown = await self._call_proxy(text_payload)
            markdown = self._append_real_metric_charts(
                markdown=markdown,
                source_text=text_payload,
            )
            status_label = "ready"
            error_message = None
        except Exception as exc:  # network/server error from external service
            logger.exception("whitepaper_generation_failed: %s", exc)
            markdown = None
            status_label = "failed"
            error_message = str(exc)[:1000]

        async with AsyncSessionFactory() as session:
            repo = WhitepaperRepository(session)
            row = await repo.get_by_id(whitepaper_id)
            if row is None:
                return
            row.status = status_label
            if markdown is not None:
                row.markdown = markdown
                row.generated_at = datetime.now(UTC)
            row.error_message = error_message
            await session.commit()

    async def _call_proxy(self, text: str) -> str:
        """Generate whitepaper markdown via the configured AI provider."""

        from app.ai.factory import get_ai_client

        client = get_ai_client()
        model = self._settings.deepseek_model_pro

        current_year = datetime.now(UTC).year
        prev_year = current_year - 1
        system = (
            "你是一位资深美业市场研究分析师，擅长将消费者调研数据转化为专业的产品洞察报告。\n\n"
            f"当前年份：{current_year}年。报告中涉及年份的描述均须以{current_year}年为基准，"
            f"不得将{prev_year}年或更早的年份描述为当前年。\n\n"
            "请根据提供的产品调研数据，生成一份结构完整、逻辑严密的美业产品消费者洞察报告（Markdown 格式）。\n\n"
            "报告要求：\n"
            "1. 使用标准 Markdown 格式（# ## ### 标题层级，**加粗**，数字/无序列表）\n"
            "2. 第一行必须是一级标题（# 标题），格式为：产品名称 + 消费者洞察报告，"
            "例如：# 彩棠多功能彩盘消费者洞察报告。\n"
            "3. 全文任何位置（包括所有章节标题、子标题、正文）禁止出现白皮书三个字。\n"
            "4. 章节结构：执行摘要 → 市场背景 → 产品概况 → 消费者洞察 → 数据分析 → "
            "卖点与顾虑 → 目标受众 → 市场建议 → 结论\n"
            "5. 语言专业、客观，使用行业术语，避免口语化\n"
            "6. 严格基于所提供的数据进行分析，不虚构数据，可适当补充行业背景\n"
            "7. 全文约 2000-3000 字\n"
            "8. 直接输出 Markdown 正文，不要在开头或结尾添加任何解释性文字"
        )

        markdown = await client.complete(
            system=system,
            user=text,
            endpoint_id=model,
        )
        if not isinstance(markdown, str) or not markdown.strip():
            raise RuntimeError("AI returned empty whitepaper content")
        return markdown

    def _build_input_text(self, product_name: str, product_description: str | None) -> str:
        """Combine product name and description into the proxy's expected input text."""

        parts = [f"产品名称：{product_name.strip() or '未命名产品'}"]
        description = (product_description or "").strip()
        if description:
            parts.append(f"产品描述：{description}")
        return "\n\n".join(parts)

    async def _build_report_enriched_description(
        self,
        *,
        user: User | None,
        evaluation_id: int,
        product_description: str | None,
    ) -> str | None:
        """Build a structured report document that mirrors the mini-program report page."""

        if user is None:
            return product_description
        try:
            from app.services.report_service import ReportService

            report = await ReportService(self.session).get_or_create_business_report(
                user=user,
                evaluation_id=evaluation_id,
            )
        except Exception as exc:
            logger.warning("whitepaper_report_context_failed: %s", exc)
            return product_description

        lines: list[str] = []

        # ── 产品名称 & 基本描述 ──
        base = (product_description or "").strip()
        if base:
            lines.append(f"产品描述：{base}")

        # ── 综合评分 ──
        avg = report.metrics.overall_intent_avg
        dist = report.metrics.intent_distribution
        total = sum(dist.values()) if dist else 0
        top2 = sum(v for k, v in dist.items() if float(k) >= 4) if dist else 0
        top2_pct = round(top2 / total * 100) if total > 0 else 0
        composite = round(avg / 5 * 100)
        grade = "S" if composite >= 90 else "A" if composite >= 75 else "B" if composite >= 60 else "C" if composite >= 45 else "D"
        lines.append(
            f"\n## 综合评分\n"
            f"综合评级：{grade}（{composite}分）\n"
            f"Top-2 Box（高意向购买率）：{top2_pct}%\n"
            f"购买意愿均值：{avg:.2f}/5"
        )

        # ── 购买意向分布 ──
        if dist:
            dist_text = "、".join(
                f"{k}分：{v}人（{round(v/total*100)}%）"
                for k, v in sorted(dist.items(), key=lambda x: x[0])
                if v > 0
            )
            lines.append(f"\n## 购买意愿分布\n{dist_text}")

        # ── 核心指标均值 ──
        dims = report.metrics.dimension_scores
        if dims:
            dim_text = "\n".join(
                f"- {self._dim_label(d.dim)}：{d.score:.2f}/5"
                for d in dims[:8]
                if d.score is not None
            )
            lines.append(f"\n## 核心指标均值\n{dim_text}")

        # ── 消费者群体分布 ──
        segs = report.metrics.persona_segments
        if segs:
            seg_text = "\n".join(
                f"- {s.segment}：购买意向均值 {s.avg_intent:.1f}/5（{s.count}人）"
                for s in segs[:6]
            )
            lines.append(f"\n## 消费者群体分布\n{seg_text}")

        # ── 正向卖点 ──
        pros = report.top_pros
        if pros:
            pros_text = "\n".join(
                f"- {p.title}（{round(p.support_count/total*100) if total else 0}%提及，{p.support_count}人）"
                for p in pros[:5]
            )
            lines.append(f"\n## 正向信号（卖点共鸣）\n{pros_text}")

        # ── 顾虑 ──
        cons = report.top_cons
        if cons:
            cons_text = "\n".join(
                f"- {c.title}（{round(c.support_count/total*100) if total else 0}%提及，{c.support_count}人）"
                for c in cons[:5]
            )
            lines.append(f"\n## 决策顾虑（失效信号）\n{cons_text}")

        # ── 价格接受度 ──
        price_items = [p for p in report.metrics.price_sensitivity if p.count > 0]
        if price_items:
            price_total = sum(p.count for p in price_items)
            price_text = "\n".join(
                f"- {p.range}：{p.count}人（{round(p.count/price_total*100)}%）"
                for p in price_items
            )
            lines.append(f"\n## 价格接受度\n{price_text}")

        # ── 目标人群与渠道 ──
        audience = report.target_audience
        if audience:
            if audience.most_likely_to_buy:
                lines.append(
                    "\n## 目标人群\n"
                    + "最可能购买：" + "、".join(audience.most_likely_to_buy[:3]) + "\n"
                    + ("最不可能购买：" + "、".join(audience.least_likely_to_buy[:3]) if audience.least_likely_to_buy else "")
                )
            if audience.channel_recommendation:
                ch_text = "\n".join(f"- {c}" for c in audience.channel_recommendation[:3])
                lines.append(f"\n## 渠道建议\n{ch_text}")

        # ── 图表数据块（原有逻辑保留） ──
        try:
            from app.services.report_service import ReportService as RS
            raw_report = await RS(self.session).get_or_create_report(
                user=user, evaluation_id=evaluation_id
            )
            chart_block = self._build_real_metric_chart_block(raw_report)
            if chart_block:
                lines.append(chart_block)
        except Exception:
            pass

        return "\n".join(lines)

    def _build_real_metric_chart_block(self, report) -> str:
        """Build deterministic chart tags from actual business report metrics."""

        charts: list[str] = []
        metrics = report.metrics
        intent_values = [
            int(metrics.intent_distribution.get(str(score), 0))
            for score in range(1, 6)
        ]
        charts.append(
            self._chart_tag(
                chart_type="bar",
                title="购买意向分布",
                labels=[f"{score}分" for score in range(1, 6)],
                datasets=[{"name": "角色数", "values": intent_values}],
            )
        )

        dimension_items = metrics.dimension_scores[:8]
        if dimension_items:
            charts.append(
                self._chart_tag(
                    chart_type="bar",
                    title="维度评分",
                    labels=[self._dim_label(item.dim) for item in dimension_items],
                    datasets=[{"name": "平均分", "values": [item.score for item in dimension_items]}],
                )
            )

        segment_items = metrics.persona_segments[:8]
        if segment_items:
            charts.append(
                self._chart_tag(
                    chart_type="bar",
                    title="人群意向对比",
                    labels=[item.segment for item in segment_items],
                    datasets=[{"name": "购买意向均分", "values": [item.avg_intent for item in segment_items]}],
                )
            )

        price_items = [item for item in metrics.price_sensitivity if item.count > 0]
        if price_items:
            charts.append(
                self._chart_tag(
                    chart_type="pie",
                    title="价格接受度",
                    labels=[item.range for item in price_items],
                    datasets=[{"name": "角色数", "values": [item.count for item in price_items]}],
                )
            )

        if not charts:
            return ""
        return "\n".join(
            [
                _CHART_BLOCK_START,
                "## 真实调研图表数据",
                "以下图表由本次角色调研 metrics 直接生成，不由大模型编写或改写。",
                *charts,
                _CHART_BLOCK_END,
            ]
        )

    def _chart_tag(
        self,
        *,
        chart_type: str,
        title: str,
        labels: list[str],
        datasets: list[dict[str, object]],
    ) -> str:
        """Render an ECharts-compatible chart tag consumed by the whitepaper HTML."""

        payload = {
            "labels": labels,
            "datasets": datasets,
        }
        data = json.dumps(payload, ensure_ascii=False)
        return f"<chart type=\"{chart_type}\" title=\"{title}\" data='{data}'></chart>"

    def _append_real_metric_charts(self, *, markdown: str, source_text: str) -> str:
        """Append deterministic chart tags to generated markdown when available."""

        chart_block = self._extract_real_metric_chart_block(source_text)
        if not chart_block:
            return markdown
        start = markdown.find(_CHART_BLOCK_START)
        end = markdown.find(_CHART_BLOCK_END)
        if start != -1 and end != -1 and end > start:
            return (
                markdown[:start].rstrip()
                + "\n\n"
                + chart_block
                + "\n"
                + markdown[end + len(_CHART_BLOCK_END):].lstrip()
            ).rstrip() + "\n"
        return markdown.rstrip() + "\n\n" + chart_block + "\n"

    def _extract_real_metric_chart_block(self, text: str) -> str:
        """Extract the deterministic chart block embedded in the generation context."""

        start = text.find(_CHART_BLOCK_START)
        end = text.find(_CHART_BLOCK_END)
        if start == -1 or end == -1 or end <= start:
            return ""
        return text[start : end + len(_CHART_BLOCK_END)]

    def _dim_label(self, dim: str) -> str:
        """Human-readable labels for PDF charts."""

        labels = {
            "channel_touchpoint": "渠道触点",
            "competitor_comparison": "竞品优势",
            "first_impression": "第一印象",
            "nps_recommendation": "推荐可信度",
            "package_appearance": "包装外观",
            "painpoint_improvement": "需求相关性",
            "price_sensitivity": "价格接受度",
            "purchase_motivation": "购买动机",
            "repurchase_intent": "复购潜力",
            "usage_scenario": "场景匹配",
        }
        return labels.get(dim, dim.replace("_", " "))

    def _to_response(self, row: Whitepaper) -> WhitepaperResponse:
        """Convert a whitepaper row into the API response shape."""

        return WhitepaperResponse(
            id=str(row.id),
            evaluation_id=str(row.evaluation_id),
            status=row.status,
            progress=self._compute_progress(row),
            product_name=_short_product_name(row.product_name),
            product_description=row.product_description,
            markdown=row.markdown,
            error_message=row.error_message,
            generated_at=self._format_dt(row.generated_at),
            created_at=self._format_dt(row.created_at),
            updated_at=self._format_dt(row.updated_at),
        )

    def _compute_progress(self, row: Whitepaper) -> int:
        """Estimate a 0-100 progress value from row status + elapsed time."""

        if row.status == "ready":
            return 100
        if row.status == "failed":
            return 0
        started = row.created_at
        if started is None:
            return 5
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        elapsed = (datetime.now(UTC) - started).total_seconds()
        if elapsed <= 0:
            return 5
        # Asymptotic curve: ramps quickly then slows, capped at 95 until ready.
        ratio = elapsed / _PROGRESS_TOTAL_SECONDS
        pct = int(min(95.0, max(5.0, ratio * 100.0)))
        return pct

    def _format_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
