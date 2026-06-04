from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.session as _db_session_module
from app.core.deps import get_db_session
from app.db.models.answer import Answer
from app.db.models.credit import CreditTransaction
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.report import Report
from app.db.models.survey import Survey
from app.db.models.user import User
from app.main import app
from app.schemas.report import DimensionRadarItem
from app.services.report_service import ReportService


@dataclass
class ReportContext:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def report_context() -> AsyncIterator[ReportContext]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(Product.__table__.create)
        await connection.run_sync(Persona.__table__.create)
        await connection.run_sync(Evaluation.__table__.create)
        await connection.run_sync(Survey.__table__.create)
        await connection.run_sync(Answer.__table__.create)
        await connection.run_sync(Report.__table__.create)
        await connection.run_sync(CreditTransaction.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    # Patch the module-level session factory so background tasks (which call
    # get_session_factory() directly, bypassing FastAPI DI) also use the
    # in-memory test database. Otherwise the async AI work commits "done" to a
    # different DB and the report fetch sees a stale "answering" status.
    _orig_factory = _db_session_module._session_factory
    _db_session_module._session_factory = session_factory

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield ReportContext(client=client, session_factory=session_factory)

    app.dependency_overrides.clear()
    _db_session_module._session_factory = _orig_factory

    # Drain fire-and-forget background tasks (e.g. dimension analysis launched
    # via asyncio.create_task) before disposing the engine, otherwise an
    # in-flight query races teardown and raises "no active connection".
    import asyncio

    pending = [
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and not task.done()
    ]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    await engine.dispose()


async def login(ctx: ReportContext, code: str) -> str:
    """Login and return token."""

    response = await ctx.client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return str(response.json()["token"])


async def create_product(ctx: ReportContext, token: str, name: str) -> str:
    """Create a product and return its ID."""

    response = await ctx.client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "description": "添加烟酰胺和神经酰胺，主打温和修护和提亮，适合日常护肤使用。",
            "image_object_keys": ["products/2026/05/123_front.jpg"],
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def create_evaluation(ctx: ReportContext, token: str, product_id: str) -> dict[str, object]:
    """Create an evaluation and return its body."""

    response = await ctx.client.post(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product_id},
    )
    assert response.status_code == 200
    return response.json()


async def generate_survey(
    ctx: ReportContext,
    token: str,
    product_id: str,
    evaluation_id: str,
) -> dict[str, object]:
    """Generate a survey for an evaluation."""

    response = await ctx.client.post(
        "/api/v1/surveys/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "product_id": product_id,
            "evaluation_id": evaluation_id,
        },
    )
    assert response.status_code == 200
    return response.json()


async def create_system_persona(
    ctx: ReportContext,
    *,
    name: str = "林雪",
    is_critical: bool = False,
    persona_tag: str = "成分党",
) -> str:
    """Create a system persona directly in DB."""

    async with ctx.session_factory() as session:
        persona = Persona(
            owner_id=None,
            name=name,
            avatar="person",
            age=28,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="产品经理",
            income_monthly=25000,
            ocean_o=70,
            ocean_c=80,
            ocean_e=50,
            ocean_a=60,
            ocean_n=55,
            persona_tag=persona_tag,
            profile={"bio": "关注成分"},
            categories=["美妆"],
            is_critical=is_critical,
            version=1,
            status="active",
        )
        session.add(persona)
        await session.commit()
        return str(persona.id)


async def prepare_done_evaluation(
    ctx: ReportContext,
    *,
    token: str,
    persona_count: int = 2,
) -> tuple[str, str]:
    """Create an evaluation, run it to done, return (evaluation_id, product_id)."""

    product_id = await create_product(ctx, token, "报告测试产品")
    evaluation = await create_evaluation(ctx, token, product_id)
    evaluation_id = str(evaluation["id"])
    await generate_survey(ctx, token, product_id, evaluation_id)

    persona_ids: list[str] = []
    persona_ids.append(
        await create_system_persona(ctx, name="林雪", is_critical=False, persona_tag="成分党")
    )
    if persona_count >= 2:
        persona_ids.append(
            await create_system_persona(ctx, name="周曼", is_critical=True, persona_tag="性价比党")
        )
    for i in range(2, persona_count):
        persona_ids.append(
            await create_system_persona(
                ctx, name=f"角色{i}", is_critical=False, persona_tag="品牌党"
            )
        )

    await ctx.client.put(
        f"/api/v1/evaluations/{evaluation_id}/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_ids": persona_ids},
    )
    run_response = await ctx.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_response.status_code == 202
    # Sync mode runs the AI work in a FastAPI background task that httpx drains
    # before the next request, so the run response itself may still be
    # "answering"; it will be "done" by the time the report is fetched below.
    assert run_response.json()["status"] in {"answering", "done"}
    return evaluation_id, product_id


async def upsert_report_pdf(
    ctx: ReportContext,
    *,
    evaluation_id: int,
    summary: str,
    pdf_url: str,
) -> str:
    """Attach a PDF url to the report for an evaluation, returning its id.

    The dimension-analysis background task launched during evaluation run may
    already have created the (unique-per-evaluation) report row, so we update an
    existing report when present and only insert when it is missing.
    """

    async with ctx.session_factory() as session:
        report = (
            await session.scalars(
                select(Report).where(Report.evaluation_id == evaluation_id)
            )
        ).first()
        if report is None:
            report = Report(
                evaluation_id=evaluation_id,
                summary=summary,
                metrics={},
                top_pros=[],
                top_cons=[],
                persona_segments={},
                pdf_url=pdf_url,
                share_token=None,
            )
            session.add(report)
        else:
            report.summary = summary
            report.pdf_url = pdf_url
        await session.commit()
        await session.refresh(report)
        return str(report.id)


async def test_report_success_for_done_evaluation(report_context: ReportContext) -> None:
    token = await login(report_context, "report_success")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_id"] == evaluation_id
    assert str(body["id"]).isdigit()
    assert body["ai_disclaimer"] == "本报告由 AI 模拟生成，仅供决策参考"
    assert body["pdf_url"] is None
    assert body["share_token"] is None


async def test_business_report_success_for_done_evaluation(report_context: ReportContext) -> None:
    token = await login(report_context, "business_report_success")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}/business",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["evaluation_id"] == evaluation_id
    assert body["template_key"] == "business_report_v1"
    assert body["decision_suggestion"]["verdict"] in {"go", "iterate", "pause"}
    assert isinstance(body["executive_summary"], list)
    assert isinstance(body["metrics"]["intent_distribution"], dict)
    assert isinstance(body["top_pros"], list)
    assert isinstance(body["top_cons"], list)
    assert isinstance(body["evidence_chains"], list)


async def test_report_generates_and_persists(report_context: ReportContext) -> None:
    token = await login(report_context, "report_persist")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    async with report_context.session_factory() as session:
        reports = (await session.scalars(select(Report))).all()
    assert len(reports) == 1
    assert reports[0].evaluation_id == int(evaluation_id)


async def test_report_idempotent_no_duplicate(report_context: ReportContext) -> None:
    token = await login(report_context, "report_idempotent")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    first = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    second = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert first.json()["id"] == second.json()["id"]
    async with report_context.session_factory() as session:
        count = len((await session.scalars(select(Report))).all())
    assert count == 1


async def test_report_overall_intent_average(report_context: ReportContext) -> None:
    token = await login(report_context, "report_avg")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    body = response.json()
    avg = body["metrics"]["overall_intent"]["average"]
    assert isinstance(avg, float)
    assert 1.0 <= avg <= 5.0


async def test_report_overall_intent_distribution(report_context: ReportContext) -> None:
    token = await login(report_context, "report_dist")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    dist = response.json()["metrics"]["overall_intent"]["distribution"]
    assert len(dist) == 5
    scores = [d["score"] for d in dist]
    assert scores == [1, 2, 3, 4, 5]
    total_count = sum(d["count"] for d in dist)
    assert total_count == 2


async def test_report_does_not_convert_1_5_intent_to_nps(report_context: ReportContext) -> None:
    service = ReportService(report_context.session_factory())
    metrics = service._calc_overall_intent(
        [
            Answer(overall_intent=5),
            Answer(overall_intent=4),
            Answer(overall_intent=1),
        ]
    )

    assert metrics.average == 3.3
    assert metrics.nps == 0


async def test_report_dimensions_radar_has_data(report_context: ReportContext) -> None:
    token = await login(report_context, "report_radar")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    radar = response.json()["metrics"]["dimensions_radar"]
    assert len(radar) > 0
    for item in radar:
        assert "dim" in item
        assert "score" in item
        assert isinstance(item["score"], (int, float))


async def test_business_report_metrics_returns_10_dimension_scores_from_mixed_answers(
    report_context: ReportContext,
) -> None:
    token = await login(report_context, "report_10_dimension_scores")
    product_id = await create_product(report_context, token, "十维雷达测试产品")
    evaluation = await create_evaluation(report_context, token, product_id)
    evaluation_id = int(str(evaluation["id"]))
    required_dims = [
        "first_impression",
        "purchase_motivation",
        "price_sensitivity",
        "package_appearance",
        "competitor_comparison",
        "usage_scenario",
        "repurchase_intent",
        "nps_recommendation",
        "channel_touchpoint",
        "painpoint_improvement",
    ]

    async with report_context.session_factory() as session:
        survey = Survey(
            evaluation_id=evaluation_id,
            product_id=int(product_id),
            questions=[
                {"id": "q01", "dim": "first_impression", "type": "open"},
                {"id": "q04", "dim": "purchase_motivation", "type": "single"},
                {"id": "q07", "dim": "price_sensitivity", "type": "open"},
                {"id": "q10", "dim": "package_appearance", "type": "multi"},
                {"id": "q13", "dim": "competitor_comparison", "type": "open"},
                {"id": "q16", "dim": "usage_scenario", "type": "open"},
                {"id": "q19", "dim": "repurchase_intent", "type": "scale_1_5"},
                {"id": "q22", "dim": "nps_recommendation", "type": "scale_1_5"},
                {"id": "q25", "dim": "channel_touchpoint", "type": "single"},
                {"id": "q28", "dim": "painpoint_improvement", "type": "open"},
            ],
            version=1,
            generated_by="ai",
        )
        persona = Persona(
            owner_id=None,
            name="角色甲",
            avatar="person",
            age=29,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="运营",
            income_monthly=18000,
            ocean_o=60,
            ocean_c=70,
            ocean_e=50,
            ocean_a=60,
            ocean_n=45,
            persona_tag="成分党",
            profile={"info_channels": ["小红书", "电商"]},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        session.add_all([survey, persona])
        await session.flush()
        entity = await session.get(Evaluation, evaluation_id)
        assert entity is not None
        entity.survey_id = survey.id
        entity.status = "done"
        entity.selected_persona_ids = [str(persona.id)]
        session.add(
            Answer(
                evaluation_id=evaluation_id,
                survey_id=survey.id,
                persona_id=persona.id,
                answers=[
                    {"qid": "q01", "type": "open", "answer": "第一眼温和清爽，愿意了解。"},
                    {"qid": "q04", "type": "single", "answer": "敏感肌需求匹配"},
                    {"qid": "q07", "type": "open", "answer": "159 元可以接受，超过 260 元会犹豫。"},
                    {"qid": "q10", "type": "multi", "answer": ["高级", "安全感", "识别度高"]},
                    {"qid": "q13", "type": "open", "answer": "比同类更温和，但差异化还要讲清楚。"},
                    {"qid": "q16", "type": "open", "answer": "换季敏感和早晚洁面都能想到使用场景。"},
                    {"qid": "q19", "type": "scale_1_5", "answer": 4, "reason": "效果稳定会复购。"},
                    {"qid": "q22", "type": "scale_1_5", "answer": 5, "reason": "会推荐给敏感肌朋友。"},
                    {"qid": "q25", "type": "single", "answer": "小红书和电商评价会影响我"},
                    {"qid": "q28", "type": "open", "answer": "能降低清洁后紧绷痛点。"},
                ],
                overall_intent=5,
                sentiment="positive",
                summary_comment="整体愿意试用，价格可接受。",
                status="done",
            )
        )
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}/business",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    scores = response.json()["metrics"]["dimension_scores"]
    dims = [item["dim"] for item in scores]
    assert dims == required_dims
    assert len(scores) == 10
    assert all(item["score"] is not None for item in scores)
    assert {"first_impression", "purchase_motivation"} <= set(dims)
    assert {"package_appearance", "usage_scenario"} <= set(dims)
    assert {"price_sensitivity", "competitor_comparison"} <= set(dims)
    assert {"repurchase_intent", "nps_recommendation"} <= set(dims)
    assert {"painpoint_improvement", "channel_touchpoint"} <= set(dims)


async def test_business_report_refreshes_stale_sparse_report_metrics_when_analysis_ready(
    report_context: ReportContext,
) -> None:
    token = await login(report_context, "report_refreshes_sparse_metrics")
    product_id = await create_product(report_context, token, "旧缓存刷新雷达测试产品")
    evaluation = await create_evaluation(report_context, token, product_id)
    evaluation_id = int(str(evaluation["id"]))
    required_dims = [
        "first_impression",
        "purchase_motivation",
        "price_sensitivity",
        "package_appearance",
        "competitor_comparison",
        "usage_scenario",
        "repurchase_intent",
        "nps_recommendation",
        "channel_touchpoint",
        "painpoint_improvement",
    ]
    ready_scores = [
        {"dim": "first_impression", "score": 82, "confidence": 0.80},
        {"dim": "purchase_motivation", "score": 78, "confidence": 0.80},
        {"dim": "price_sensitivity", "score": 62, "confidence": 0.70},
        {"dim": "package_appearance", "score": 80, "confidence": 0.75},
        {"dim": "competitor_comparison", "score": 66, "confidence": 0.70},
        {"dim": "usage_scenario", "score": 76, "confidence": 0.76},
        {"dim": "repurchase_intent", "score": 70, "confidence": 0.72},
        {"dim": "nps_recommendation", "score": 74, "confidence": 0.74},
        {"dim": "channel_touchpoint", "score": 68, "confidence": 0.70},
        {"dim": "painpoint_improvement", "score": 77, "confidence": 0.78},
    ]

    async with report_context.session_factory() as session:
        survey = Survey(
            evaluation_id=evaluation_id,
            product_id=int(product_id),
            questions=[
                {"id": "q01", "dim": "first_impression", "type": "open"},
                {"id": "q04", "dim": "purchase_motivation", "type": "single"},
                {"id": "q07", "dim": "price_sensitivity", "type": "open"},
                {"id": "q10", "dim": "package_appearance", "type": "multi"},
                {"id": "q13", "dim": "competitor_comparison", "type": "open"},
                {"id": "q16", "dim": "usage_scenario", "type": "open"},
                {"id": "q19", "dim": "repurchase_intent", "type": "scale_1_5"},
                {"id": "q22", "dim": "nps_recommendation", "type": "scale_1_5"},
                {"id": "q25", "dim": "channel_touchpoint", "type": "single"},
                {"id": "q28", "dim": "painpoint_improvement", "type": "open"},
            ],
            version=1,
            generated_by="ai",
        )
        persona = Persona(
            owner_id=None,
            name="角色乙",
            avatar="person",
            age=31,
            gender="female",
            city="杭州",
            city_tier=1,
            occupation="市场",
            income_monthly=20000,
            ocean_o=60,
            ocean_c=70,
            ocean_e=50,
            ocean_a=60,
            ocean_n=45,
            persona_tag="功效党",
            profile={"info_channels": ["小红书"]},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        session.add_all([survey, persona])
        await session.flush()
        entity = await session.get(Evaluation, evaluation_id)
        assert entity is not None
        entity.survey_id = survey.id
        entity.status = "done"
        entity.selected_persona_ids = [str(persona.id)]
        session.add(
            Answer(
                evaluation_id=evaluation_id,
                survey_id=survey.id,
                persona_id=persona.id,
                answers=[
                    {"qid": "q01", "type": "open", "answer": "第一眼愿意了解。"},
                    {"qid": "q04", "type": "single", "answer": "购买理由明确"},
                    {"qid": "q07", "type": "open", "answer": "159 元可以接受。"},
                    {"qid": "q10", "type": "multi", "answer": ["高级", "安心"]},
                    {"qid": "q13", "type": "open", "answer": "比同类更温和。"},
                    {"qid": "q16", "type": "open", "answer": "换季敏感可以使用。"},
                    {"qid": "q19", "type": "scale_1_5", "answer": 4},
                    {"qid": "q22", "type": "scale_1_5", "answer": 5},
                    {"qid": "q25", "type": "single", "answer": "小红书会影响购买"},
                    {"qid": "q28", "type": "open", "answer": "能降低紧绷痛点。"},
                ],
                overall_intent=5,
                sentiment="positive",
                summary_comment="整体愿意购买。",
                status="done",
            )
        )
        session.add(
            Report(
                evaluation_id=evaluation_id,
                summary="旧缓存报告",
                metrics={
                    "overall_intent": {
                        "average": 5,
                        "distribution": [{"score": s, "count": 1 if s == 5 else 0} for s in range(1, 6)],
                        "nps": 0,
                    },
                    "dimensions_radar": [
                        {"dim": "repurchase_intent", "score": 4.0},
                        {"dim": "nps_recommendation", "score": 5.0},
                    ],
                    "price_sensitivity": {"median_acceptable_price": 0, "distribution": []},
                    "segment_intent": [],
                },
                top_pros=[],
                top_cons=[],
                persona_segments={
                    "most_positive": [],
                    "most_negative": [],
                    "highest_value": [],
                },
                dimension_analysis=ready_scores,
                dimension_analysis_status="ready",
            )
        )
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}/business",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    scores = response.json()["metrics"]["dimension_scores"]
    dims = [item["dim"] for item in scores]
    assert dims == required_dims
    assert len(scores) == 10
    assert dims[6:] != ["repurchase_intent", "nps_recommendation"]
    async with report_context.session_factory() as session:
        refreshed = (
            await session.execute(select(Report).where(Report.evaluation_id == evaluation_id))
        ).scalar_one()
        stored_dims = [item["dim"] for item in refreshed.metrics["dimensions_radar"]]
    assert stored_dims == required_dims


async def test_report_top_pros_has_data(report_context: ReportContext) -> None:
    token = await login(report_context, "report_pros")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    top_pros = response.json()["top_pros"]
    assert len(top_pros) >= 1
    assert top_pros[0]["support_count"] > 0
    assert len(top_pros[0]["quotes"]) > 0
    assert "persona_id" in top_pros[0]["quotes"][0]
    assert "persona_name" in top_pros[0]["quotes"][0]
    assert "quote" in top_pros[0]["quotes"][0]


async def test_report_top_cons_has_data(report_context: ReportContext) -> None:
    token = await login(report_context, "report_cons")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    top_cons = response.json()["top_cons"]
    assert len(top_cons) >= 1
    assert top_cons[0]["support_count"] > 0
    assert len(top_cons[0]["quotes"]) > 0


async def test_report_persona_segments(report_context: ReportContext) -> None:
    token = await login(report_context, "report_segments")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    segments = response.json()["persona_segments"]
    assert "most_positive" in segments
    assert "most_negative" in segments
    assert "highest_value" in segments
    assert len(segments["most_positive"]) > 0
    assert len(segments["most_negative"]) > 0
    assert len(segments["highest_value"]) > 0


async def test_report_cross_user_fails(report_context: ReportContext) -> None:
    owner_token = await login(report_context, "report_owner")
    other_token = await login(report_context, "report_other")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=owner_token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EVALUATION_NOT_FOUND"


async def test_report_not_done_fails(report_context: ReportContext) -> None:
    token = await login(report_context, "report_not_done")
    product_id = await create_product(report_context, token, "未完成产品")
    evaluation = await create_evaluation(report_context, token, product_id)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "EVALUATION_NOT_READY"


async def test_report_no_answers_fails(report_context: ReportContext) -> None:
    token = await login(report_context, "report_no_answers")
    product_id = await create_product(report_context, token, "无答题产品")
    evaluation = await create_evaluation(report_context, token, product_id)

    async with report_context.session_factory() as session:
        entity = await session.get(Evaluation, int(str(evaluation["id"])))
        assert entity is not None
        entity.status = "done"
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "EVALUATION_NOT_READY"


async def test_report_no_token_fails(report_context: ReportContext) -> None:
    response = await report_context.client.get("/api/v1/reports/by-evaluation/1")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


async def test_report_nonexistent_evaluation_fails(report_context: ReportContext) -> None:
    token = await login(report_context, "report_nonexist")

    response = await report_context.client.get(
        "/api/v1/reports/by-evaluation/999999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "EVALUATION_NOT_FOUND"


async def test_report_path_visible_in_openapi(report_context: ReportContext) -> None:
    response = await report_context.client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/reports/by-evaluation/{evaluation_id}" in paths


async def test_list_report_pdfs_returns_current_user_pdfs(report_context: ReportContext) -> None:
    token = await login(report_context, "report_pdf_list")
    evaluation_id, product_id = await prepare_done_evaluation(report_context, token=token)

    report_id = await upsert_report_pdf(
        report_context,
        evaluation_id=int(evaluation_id),
        summary="pdf report",
        pdf_url="/static/reports/user/evaluation.pdf",
    )

    response = await report_context.client.get(
        "/api/v1/reports/pdfs",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [
        {
            "report_id": report_id,
            "evaluation_id": evaluation_id,
            "product_name": "报告测试产品",
            "pdf_title": "evaluation",
            "pdf_url": "/static/reports/user/evaluation.pdf",
            "generated_at": body["items"][0]["generated_at"],
        }
    ]
    assert product_id.isdigit()


async def test_delete_report_pdfs_only_deletes_current_user_reports(
    report_context: ReportContext,
) -> None:
    owner_token = await login(report_context, "report_pdf_delete_owner")
    other_token = await login(report_context, "report_pdf_delete_other")
    owner_evaluation_id, _ = await prepare_done_evaluation(report_context, token=owner_token)
    other_evaluation_id, _ = await prepare_done_evaluation(report_context, token=other_token)

    owner_report_id = await upsert_report_pdf(
        report_context,
        evaluation_id=int(owner_evaluation_id),
        summary="owner pdf report",
        pdf_url="/static/reports/owner.pdf",
    )
    other_report_id = await upsert_report_pdf(
        report_context,
        evaluation_id=int(other_evaluation_id),
        summary="other pdf report",
        pdf_url="/static/reports/other.pdf",
    )

    response = await report_context.client.post(
        "/api/v1/reports/pdfs/delete",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"report_ids": [owner_report_id, other_report_id]},
    )

    assert response.status_code == 204

    owner_list = await report_context.client.get(
        "/api/v1/reports/pdfs",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    other_list = await report_context.client.get(
        "/api/v1/reports/pdfs",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert owner_list.status_code == 200
    assert owner_list.json()["items"] == []
    assert other_list.status_code == 200
    assert [item["report_id"] for item in other_list.json()["items"]] == [other_report_id]


async def test_report_summary_contains_count(report_context: ReportContext) -> None:
    token = await login(report_context, "report_summary")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    summary = response.json()["summary"]
    assert "2" in summary
    assert "角色" in summary


async def test_report_segment_intent_has_data(report_context: ReportContext) -> None:
    token = await login(report_context, "report_seg_intent")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    seg = response.json()["metrics"]["segment_intent"]
    assert len(seg) > 0
    for item in seg:
        assert "segment" in item
        assert "count" in item
        assert "avg_intent" in item


async def test_business_report_uses_real_answer_evidence(
    report_context: ReportContext,
) -> None:
    token = await login(report_context, "report_real_evidence")
    product_id = await create_product(report_context, token, "真实证据报告产品")
    evaluation = await create_evaluation(report_context, token, product_id)
    evaluation_id = int(str(evaluation["id"]))

    async with report_context.session_factory() as session:
        survey = Survey(
            evaluation_id=evaluation_id,
            product_id=int(product_id),
            questions=[
                {"id": "q01", "dim": "purchase_motivation", "type": "scale_1_5"},
                {"id": "q02", "dim": "price_sensitivity", "type": "open"},
                {"id": "q03", "dim": "painpoint_improvement", "type": "open"},
            ],
            version=1,
            generated_by="ai",
        )
        session.add(survey)
        await session.flush()
        entity = await session.get(Evaluation, evaluation_id)
        assert entity is not None
        entity.survey_id = survey.id
        entity.status = "done"
        persona_a = Persona(
            owner_id=None,
            name="李敏",
            avatar="person",
            age=31,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="品牌经理",
            income_monthly=22000,
            ocean_o=70,
            ocean_c=80,
            ocean_e=50,
            ocean_a=60,
            ocean_n=40,
            persona_tag="成分党",
            profile={"info_channels": ["小红书", "朋友推荐"]},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        persona_b = Persona(
            owner_id=None,
            name="周晨",
            avatar="person",
            age=35,
            gender="female",
            city="杭州",
            city_tier=2,
            occupation="运营负责人",
            income_monthly=18000,
            ocean_o=50,
            ocean_c=75,
            ocean_e=45,
            ocean_a=55,
            ocean_n=60,
            persona_tag="性价比党",
            profile={"info_channels": ["直播间", "电商评价"]},
            categories=["美妆"],
            is_critical=True,
            version=1,
            status="active",
        )
        session.add_all([persona_a, persona_b])
        await session.flush()
        entity.selected_persona_ids = [str(persona_a.id), str(persona_b.id)]
        session.add_all(
            [
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=persona_a.id,
                    answers=[
                        {
                            "qid": "q01",
                            "type": "scale_1_5",
                            "answer": 5,
                            "reason": "核心卖点是温和修护，和敏感肌需求很贴。",
                        },
                        {
                            "qid": "q02",
                            "type": "open",
                            "answer": "我觉得 189 元可以接受，超过 260 元就要犹豫。",
                            "reason": "价格在成分功效合理范围内。",
                        },
                        {
                            "qid": "q03",
                            "type": "open",
                            "answer": "主打温和修护让我有尝试意愿。",
                            "reason": "屏障修护诉求明确。",
                        },
                    ],
                    overall_intent=5,
                    sentiment="positive",
                    summary_comment="温和修护和敏感肌场景很贴，189 元我能接受。",
                    status="done",
                ),
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=persona_b.id,
                    answers=[
                        {
                            "qid": "q01",
                            "type": "scale_1_5",
                            "answer": 2,
                            "reason": "如果没有更多真实测评，我不会立刻下单。",
                        },
                        {
                            "qid": "q02",
                            "type": "open",
                            "answer": "129 元以内会考虑，超过 199 元感觉偏贵。",
                            "reason": "同类产品选择很多，价格要有优势。",
                        },
                        {
                            "qid": "q03",
                            "type": "open",
                            "answer": "担心功效证据不足。",
                            "reason": "需要看到更多用户反馈或检测依据。",
                        },
                    ],
                    overall_intent=2,
                    sentiment="negative",
                    summary_comment="价格和真实证据是主要顾虑。",
                    status="done",
                ),
            ]
        )
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}/business",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    channel_recommendations = body["target_audience"]["channel_recommendation"]
    joined_channels = "\n".join(channel_recommendations)
    assert "小红书" in joined_channels
    assert "朋友推荐" in joined_channels
    assert "成分党" in joined_channels
    assert "电商详情页" not in joined_channels
    assert "角色原话" not in joined_channels
    price_counts = {
        item["range"]: item["count"]
        for item in body["metrics"]["price_sensitivity"]
    }
    assert price_counts == {"100-200": 2}
    joined = "\n".join(
        body["executive_summary"]
        + body["next_test_recommendations"]
        + [item["business_implication"] for item in body["top_pros"]]
        + [item["improvement_suggestion"] for item in body["top_cons"]]
    )
    assert "Average intent" not in joined
    assert "content seeding" not in joined
    assert "温和修护" in joined
    assert "真实测评" in joined or "功效证据" in joined


async def test_report_theme_support_count_matches_dialogue_mentions(
    report_context: ReportContext,
) -> None:
    token = await login(report_context, "report_theme_mentions")
    product_id = await create_product(report_context, token, "品牌背书产品")
    evaluation = await create_evaluation(report_context, token, product_id)
    evaluation_id = int(str(evaluation["id"]))

    async with report_context.session_factory() as session:
        survey = Survey(
            evaluation_id=evaluation_id,
            product_id=int(product_id),
            questions=[{"id": "q01", "dim": "purchase_motivation", "type": "open"}],
            version=1,
            generated_by="ai",
        )
        session.add(survey)
        await session.flush()
        entity = await session.get(Evaluation, evaluation_id)
        assert entity is not None
        entity.survey_id = survey.id
        entity.status = "done"
        personas = [
            Persona(
                owner_id=None,
                name=f"角色{i}",
                avatar="person",
                age=28 + i,
                gender="female",
                city="上海",
                city_tier=1,
                occupation="白领",
                income_monthly=18000,
                ocean_o=60,
                ocean_c=70,
                ocean_e=50,
                ocean_a=60,
                ocean_n=45,
                persona_tag=f"品牌关注群体{i}",
                profile={"info_channels": ["小红书"]},
                categories=["护肤"],
                is_critical=False,
                version=1,
                status="active",
            )
            for i in range(1, 4)
        ]
        session.add_all(personas)
        await session.flush()
        entity.selected_persona_ids = [str(persona.id) for persona in personas]
        session.add_all(
            [
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=personas[0].id,
                    answers=[{
                        "qid": "q01",
                        "type": "open",
                        "answer": "欧莱雅这种大牌背书让我觉得更可信。",
                        "reason": "大牌背书是主要正向原因。",
                    }],
                    overall_intent=5,
                    sentiment="positive",
                    summary_comment="认可欧莱雅大牌背书。",
                    status="done",
                ),
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=personas[1].id,
                    answers=[{
                        "qid": "q01",
                        "type": "open",
                        "answer": "品牌是欧莱雅会增加信任感。",
                        "reason": "品牌可信度比较强。",
                    }],
                    overall_intent=3,
                    sentiment="neutral",
                    summary_comment="品牌背书有帮助，但还想看价格。",
                    status="done",
                ),
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=personas[2].id,
                    answers=[{
                        "qid": "q01",
                        "type": "open",
                        "answer": "如果是欧莱雅旗下产品，大品牌让我更愿意了解。",
                        "reason": "大品牌可信。",
                    }],
                    overall_intent=2,
                    sentiment="negative",
                    summary_comment="仍担心价格，但认可大品牌。",
                    status="done",
                ),
            ]
        )
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}/business",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    brand_item = next(
        item for item in body["top_pros"]
        if "品牌" in item["title"] or "大牌" in item["title"] or "欧莱雅" in item["title"]
    )
    assert brand_item["support_count"] == 3
    assert len(brand_item["evidence_quotes"]) == 3


async def test_resolve_dimensions_radar_returns_all_ready_llm_scores(
    report_context: ReportContext,
) -> None:
    service = ReportService(report_context.session_factory())
    rule = [DimensionRadarItem(dim="first_impression", score=4.0)]
    report = Report(
        evaluation_id=1,
        dimension_analysis=[
            {"dim": "first_impression", "score": 82, "confidence": 0.80},
            {"dim": "purchase_motivation", "score": 78, "confidence": 0.80},
            {"dim": "price_sensitivity", "score": 62, "confidence": 0.70},
            {"dim": "package_appearance", "score": 80, "confidence": 0.75},
            {"dim": "competitor_comparison", "score": 66, "confidence": 0.70},
            {"dim": "usage_scenario", "score": 76, "confidence": 0.76},
            {"dim": "repurchase_intent", "score": 70, "confidence": 0.72},
            {"dim": "nps_recommendation", "score": 74, "confidence": 0.74},
            {"dim": "channel_touchpoint", "score": 68, "confidence": 0.70},
            {"dim": "painpoint_improvement", "score": 77, "confidence": 0.78},
        ],
        dimension_analysis_status="ready",
    )
    result = service._resolve_dimensions_radar(rule, report)

    assert [item.dim for item in result] == [
        "first_impression",
        "purchase_motivation",
        "price_sensitivity",
        "package_appearance",
        "competitor_comparison",
        "usage_scenario",
        "repurchase_intent",
        "nps_recommendation",
        "channel_touchpoint",
        "painpoint_improvement",
    ]
    assert [item.score for item in result] == [82, 78, 62, 80, 66, 76, 70, 74, 68, 77]


async def test_build_dimension_inputs_keeps_all_10_dims_and_mixed_answer_types(
    report_context: ReportContext,
) -> None:
    service = ReportService(report_context.session_factory())
    survey = Survey(
        questions=[
            {"id": "q01", "dim": "first_impression", "type": "open", "title": "第一眼感觉"},
            {"id": "q04", "dim": "purchase_motivation", "type": "single", "title": "购买理由"},
            {"id": "q07", "dim": "price_sensitivity", "type": "open", "title": "价格"},
            {"id": "q10", "dim": "package_appearance", "type": "multi", "title": "包装"},
            {"id": "q13", "dim": "competitor_comparison", "type": "open", "title": "竞品"},
            {"id": "q16", "dim": "usage_scenario", "type": "open", "title": "场景"},
            {"id": "q19", "dim": "repurchase_intent", "type": "scale_1_5", "title": "复购"},
            {"id": "q22", "dim": "nps_recommendation", "type": "scale_1_5", "title": "推荐"},
            {"id": "q25", "dim": "channel_touchpoint", "type": "single", "title": "渠道"},
            {"id": "q28", "dim": "painpoint_improvement", "type": "open", "title": "痛点"},
        ]
    )
    answers = [
        Answer(
            persona_id=11,
            answers=[
                {"qid": "q01", "type": "open", "answer": "第一眼温和，愿意试试"},
                {"qid": "q04", "type": "single", "answer": "敏感肌需求匹配"},
                {"qid": "q10", "type": "multi", "answer": ["高级", "安全感"]},
                {"qid": "q19", "type": "scale_1_5", "answer": 4, "reason": "愿意复购"},
            ],
            overall_intent=4,
            sentiment="positive",
            summary_comment="整体愿意进一步了解。",
        )
    ]

    inputs = service._build_dimension_inputs(survey, answers, personas={})

    assert [item["dim"] for item in inputs] == [
        "first_impression",
        "purchase_motivation",
        "price_sensitivity",
        "package_appearance",
        "competitor_comparison",
        "usage_scenario",
        "repurchase_intent",
        "nps_recommendation",
        "channel_touchpoint",
        "painpoint_improvement",
    ]
    first = inputs[0]
    package = inputs[3]
    repurchase = inputs[6]
    assert first["has_data"] is True
    assert first["answers"][0]["type"] == "open"
    assert first["answers"][0]["text"] == "第一眼温和，愿意试试"
    assert package["answers"][0]["type"] == "multi"
    assert package["answers"][0]["text"] == "高级 安全感"
    assert repurchase["answers"][0]["type"] == "scale_1_5"
    assert repurchase["answers"][0]["score"] == 4
    assert inputs[2]["has_data"] is False


async def test_resolve_dimensions_radar_falls_back_when_not_ready(
    report_context: ReportContext,
) -> None:
    service = ReportService(report_context.session_factory())
    rule = [DimensionRadarItem(dim="first_impression", score=4.0)]

    generating = Report(
        evaluation_id=1,
        dimension_analysis=None,
        dimension_analysis_status="generating",
    )
    assert service._resolve_dimensions_radar(rule, generating) == rule
    assert service._resolve_dimensions_radar(rule, None) == rule

    # ready but empty payload -> still fall back, never return an empty radar
    empty = Report(
        evaluation_id=1,
        dimension_analysis=[],
        dimension_analysis_status="ready",
    )
    assert service._resolve_dimensions_radar(rule, empty) == rule


async def test_theme_quote_matches_its_theme_across_multiple_questions(
    report_context: ReportContext,
) -> None:
    token = await login(report_context, "report_theme_quote_match")
    product_id = await create_product(report_context, token, "多题主题归因产品")
    evaluation = await create_evaluation(report_context, token, product_id)
    evaluation_id = int(str(evaluation["id"]))

    async with report_context.session_factory() as session:
        survey = Survey(
            evaluation_id=evaluation_id,
            product_id=int(product_id),
            questions=[
                {"id": "q01", "dim": "purchase_motivation", "type": "open"},
                {"id": "q02", "dim": "price_sensitivity", "type": "open"},
                {"id": "q03", "dim": "painpoint_improvement", "type": "open"},
            ],
            version=1,
            generated_by="ai",
        )
        session.add(survey)
        await session.flush()
        entity = await session.get(Evaluation, evaluation_id)
        assert entity is not None
        entity.survey_id = survey.id
        entity.status = "done"
        persona_a = Persona(
            owner_id=None,
            name="林雪",
            avatar="person",
            age=29,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="产品经理",
            income_monthly=22000,
            ocean_o=70,
            ocean_c=80,
            ocean_e=50,
            ocean_a=60,
            ocean_n=45,
            persona_tag="成分党",
            profile={},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        persona_b = Persona(
            owner_id=None,
            name="周曼",
            avatar="person",
            age=33,
            gender="female",
            city="杭州",
            city_tier=2,
            occupation="运营",
            income_monthly=17000,
            ocean_o=55,
            ocean_c=70,
            ocean_e=50,
            ocean_a=55,
            ocean_n=50,
            persona_tag="性价比党",
            profile={},
            categories=["美妆"],
            is_critical=True,
            version=1,
            status="active",
        )
        session.add_all([persona_a, persona_b])
        await session.flush()
        entity.selected_persona_ids = [str(persona_a.id), str(persona_b.id)]
        session.add_all(
            [
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=persona_a.id,
                    answers=[
                        {
                            "qid": "q01",
                            "type": "open",
                            "answer": "欧莱雅大牌我比较信。",
                            "reason": "品牌背书让我更想了解。",
                        },
                        {
                            "qid": "q02",
                            "type": "open",
                            "answer": "到手价两百多太贵了。",
                            "reason": "价格超预算我会犹豫。",
                        },
                        {
                            "qid": "q03",
                            "type": "open",
                            "answer": "希望温和不刺激。",
                            "reason": "敏感肌怕刺激，看重温和修护。",
                        },
                    ],
                    overall_intent=4,
                    sentiment="positive",
                    summary_comment="认可品牌，但价格偏贵。",
                    status="done",
                ),
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=persona_b.id,
                    answers=[
                        {
                            "qid": "q01",
                            "type": "open",
                            "answer": "是欧莱雅旗下产品，信任感强。",
                            "reason": "大牌可信。",
                        },
                        {
                            "qid": "q02",
                            "type": "open",
                            "answer": "一百以内我会下单。",
                            "reason": "看预期到手价。",
                        },
                        {
                            "qid": "q03",
                            "type": "open",
                            "answer": "担心功效不够。",
                            "reason": "不确定有没有用。",
                        },
                    ],
                    overall_intent=3,
                    sentiment="neutral",
                    summary_comment="认可大牌，担心功效。",
                    status="done",
                ),
            ]
        )
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    top_pros = body["top_pros"]
    top_cons = body["top_cons"]

    # 品牌背书：两位角色的 q01 都提到 -> support_count 是真实提及人数，不虚高
    brand_pro = next(p for p in top_pros if "品牌" in p["title"] or "背书" in p["title"])
    assert brand_pro["support_count"] == 2

    # 价格顾虑：只有林雪的 q02 提到 -> support_count == 1
    price_con = next(c for c in top_cons if "价格" in c["title"])
    assert price_con["support_count"] == 1
    # 关键回归点：价格主题的证据 quote 必须来自真正谈价格的那道题，
    # 而不是错配成 q01 里讲品牌的话。
    price_quote = price_con["quotes"][0]["quote"]
    assert any(word in price_quote for word in ["价格", "预算", "贵"])
    assert "品牌" not in price_quote
    assert "欧莱雅" not in price_quote


async def test_existing_report_is_refreshed_from_real_answers(
    report_context: ReportContext,
) -> None:
    token = await login(report_context, "report_refresh_existing")
    product_id = await create_product(report_context, token, "旧报告刷新产品")
    evaluation = await create_evaluation(report_context, token, product_id)
    evaluation_id = int(str(evaluation["id"]))

    async with report_context.session_factory() as session:
        survey = Survey(
            evaluation_id=evaluation_id,
            product_id=int(product_id),
            questions=[
                {"id": "q01", "dim": "purchase_motivation", "type": "scale_1_5"},
                {"id": "q02", "dim": "price_sensitivity", "type": "open"},
            ],
            version=1,
            generated_by="ai",
        )
        persona = Persona(
            owner_id=None,
            name="陈然",
            avatar="person",
            age=29,
            gender="female",
            city="广州",
            city_tier=1,
            occupation="内容运营",
            income_monthly=16000,
            ocean_o=70,
            ocean_c=70,
            ocean_e=55,
            ocean_a=60,
            ocean_n=45,
            persona_tag="功效派",
            profile={},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        session.add_all([survey, persona])
        await session.flush()
        entity = await session.get(Evaluation, evaluation_id)
        assert entity is not None
        entity.survey_id = survey.id
        entity.status = "done"
        entity.selected_persona_ids = [str(persona.id)]
        session.add(
            Answer(
                evaluation_id=evaluation_id,
                survey_id=survey.id,
                persona_id=persona.id,
                answers=[
                    {
                        "qid": "q01",
                        "type": "scale_1_5",
                        "answer": 5,
                        "reason": "真实测评和温和修护让我愿意尝试。",
                    },
                    {
                        "qid": "q02",
                        "type": "open",
                        "answer": "159 元我可以接受。",
                        "reason": "价格和功效匹配。",
                    },
                ],
                overall_intent=5,
                sentiment="positive",
                summary_comment="真实测评能增强信任。",
                status="done",
            )
        )
        session.add(
            Report(
                evaluation_id=evaluation_id,
                summary="old cached summary",
                metrics={
                    "overall_intent": {
                        "average": 1.0,
                        "distribution": [{"score": score, "count": 0} for score in range(1, 6)],
                        "nps": -100,
                    },
                    "dimensions_radar": [],
                    "price_sensitivity": {
                        "median_acceptable_price": 0,
                        "distribution": [],
                    },
                    "segment_intent": [],
                },
                top_pros=[],
                top_cons=[],
                persona_segments={},
                pdf_url=None,
                share_token=None,
            )
        )
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}/business",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["overall_intent_avg"] == 5.0
    assert body["metrics"]["price_sensitivity"][0]["range"] == "100-200"
    assert "old cached summary" not in "\n".join(body["executive_summary"])


async def test_business_report_restores_soft_deleted_report_instead_of_inserting_duplicate(
    report_context: ReportContext,
) -> None:
    token = await login(report_context, "report_restore_deleted")
    product_id = await create_product(report_context, token, "软删除报告恢复产品")
    evaluation = await create_evaluation(report_context, token, product_id)
    evaluation_id = int(str(evaluation["id"]))

    async with report_context.session_factory() as session:
        survey = Survey(
            evaluation_id=evaluation_id,
            product_id=int(product_id),
            questions=[{"id": "q01", "dim": "purchase_motivation", "type": "scale_1_5"}],
            version=1,
            generated_by="ai",
        )
        persona = Persona(
            owner_id=None,
            name="角色甲",
            avatar="person",
            age=28,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="运营",
            income_monthly=15000,
            ocean_o=60,
            ocean_c=70,
            ocean_e=50,
            ocean_a=60,
            ocean_n=45,
            persona_tag="成分党",
            profile={},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        session.add_all([survey, persona])
        await session.flush()
        entity = await session.get(Evaluation, evaluation_id)
        assert entity is not None
        entity.survey_id = survey.id
        entity.status = "done"
        entity.selected_persona_ids = [str(persona.id)]
        session.add(
            Answer(
                evaluation_id=evaluation_id,
                survey_id=survey.id,
                persona_id=persona.id,
                answers=[
                    {
                        "qid": "q01",
                        "type": "scale_1_5",
                        "answer": 4,
                        "reason": "卖点清楚，愿意进一步了解。",
                    }
                ],
                overall_intent=4,
                sentiment="positive",
                summary_comment="卖点清楚。",
                status="done",
            )
        )
        session.add(
            Report(
                evaluation_id=evaluation_id,
                summary="soft deleted",
                metrics={},
                top_pros=[],
                top_cons=[],
                persona_segments={},
                pdf_url=None,
                share_token=None,
                deleted_at=datetime.now(UTC),
            )
        )
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}/business",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["metrics"]["overall_intent_avg"] == 4.0
    async with report_context.session_factory() as session:
        reports = (await session.scalars(select(Report))).all()
    matching = [report for report in reports if report.evaluation_id == evaluation_id]
    assert len(matching) == 1
    assert matching[0].deleted_at is None


async def test_business_report_uses_persona_groups_not_names(
    report_context: ReportContext,
) -> None:
    token = await login(report_context, "report_persona_group_only")
    product_id = await create_product(report_context, token, "角色群类报告产品")
    evaluation = await create_evaluation(report_context, token, product_id)
    evaluation_id = int(str(evaluation["id"]))

    async with report_context.session_factory() as session:
        survey = Survey(
            evaluation_id=evaluation_id,
            product_id=int(product_id),
            questions=[
                {"id": "q01", "dim": "purchase_motivation", "type": "scale_1_5"},
                {"id": "q02", "dim": "price_sensitivity", "type": "open"},
            ],
            version=1,
            generated_by="ai",
        )
        session.add(survey)
        await session.flush()
        entity = await session.get(Evaluation, evaluation_id)
        assert entity is not None
        entity.survey_id = survey.id
        entity.status = "done"
        persona_a = Persona(
            owner_id=None,
            name="林雪",
            avatar="person",
            age=28,
            gender="female",
            city="上海",
            city_tier=1,
            occupation="产品经理",
            income_monthly=25000,
            ocean_o=70,
            ocean_c=80,
            ocean_e=50,
            ocean_a=60,
            ocean_n=55,
            persona_tag="成分党",
            profile={},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        persona_b = Persona(
            owner_id=None,
            name="周曼",
            avatar="person",
            age=34,
            gender="female",
            city="杭州",
            city_tier=2,
            occupation="运营",
            income_monthly=18000,
            ocean_o=50,
            ocean_c=75,
            ocean_e=45,
            ocean_a=55,
            ocean_n=60,
            persona_tag="性价比党",
            profile={},
            categories=["美妆"],
            is_critical=True,
            version=1,
            status="active",
        )
        session.add_all([persona_a, persona_b])
        await session.flush()
        entity.selected_persona_ids = [str(persona_a.id), str(persona_b.id)]
        session.add_all(
            [
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=persona_a.id,
                    answers=[
                        {
                            "qid": "q01",
                            "type": "scale_1_5",
                            "answer": 5,
                            "reason": "温和修护和成分逻辑清晰。",
                        },
                        {
                            "qid": "q02",
                            "type": "open",
                            "answer": "189 元可以接受。",
                            "reason": "价格和功效匹配。",
                        },
                    ],
                    overall_intent=5,
                    sentiment="positive",
                    summary_comment="成分逻辑清晰，愿意尝试。",
                    status="done",
                ),
                Answer(
                    evaluation_id=evaluation_id,
                    survey_id=survey.id,
                    persona_id=persona_b.id,
                    answers=[
                        {
                            "qid": "q01",
                            "type": "scale_1_5",
                            "answer": 2,
                            "reason": "如果没有真实测评，我会担心不值这个价格。",
                        },
                        {
                            "qid": "q02",
                            "type": "open",
                            "answer": "129 元以内会考虑。",
                            "reason": "价格需要更有优势。",
                        },
                    ],
                    overall_intent=2,
                    sentiment="negative",
                    summary_comment="主要顾虑是价格和证据。",
                    status="done",
                ),
            ]
        )
        await session.commit()

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}/business",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body_text = response.text
    assert "林雪" not in body_text
    assert "周曼" not in body_text
    assert "成分党" in body_text
    assert "性价比党" in body_text
    assert "位角色" not in body_text
    assert "类角色标签所属群体" in body_text
    assert "成分党这一类角色标签所属群体支持这一信号" in body_text
    assert "性价比党这一类角色标签所属群体暴露该风险" in body_text

    base_response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert base_response.status_code == 200
    base_text = base_response.text
    assert "林雪" not in base_text
    assert "周曼" not in base_text
    assert "成分党" in base_text
    assert "性价比党" in base_text
