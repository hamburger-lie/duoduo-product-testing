from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ai.client import AIClient


class ReportSynthesizeAdapter:
    """AI adapter for report text generation.

    Currently used for narrative summary only.
    Metrics (radar, distribution, NPS) remain rule-based in ReportService.
    """

    def __init__(self, ai_client: AIClient | None = None) -> None:
        self._ai_client = ai_client

    async def generate_summary(
        self,
        *,
        product_summary: dict[str, object],
        all_answers: list[dict[str, object]],
    ) -> str:
        """Generate a narrative summary using the report_synthesize.j2 prompt."""

        from app.ai.factory import get_ai_client
        from app.ai.models import ModelRouter, TaskType
        from app.ai.prompt_manager import render_prompt

        ai_client = self._ai_client or get_ai_client()
        route = ModelRouter().get(TaskType.REPORT_SYNTHESIZE)

        prompt, _, _ = render_prompt(
            "report_synthesize",
            user_role_type="manufacturer",
            product_ai_summary=product_summary,
            survey_questions=[],
            all_answers=all_answers,
            report_template={},
        )

        return await ai_client.complete(
            system=(
                "你是美妆行业市场调研分析师。"
                "请根据测评数据生成简洁的执行摘要，不超过 200 字。"
            ),
            user=prompt,
            endpoint_id=route.endpoint_id,
        )
