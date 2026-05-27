from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

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

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield ReportContext(client=client, session_factory=session_factory)

    app.dependency_overrides.clear()
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
    assert run_response.json()["status"] == "done"
    return evaluation_id, product_id


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

    async with report_context.session_factory() as session:
        report = Report(
            evaluation_id=int(evaluation_id),
            summary="pdf report",
            metrics={},
            top_pros=[],
            top_cons=[],
            persona_segments={},
            pdf_url="/static/reports/user/evaluation.pdf",
            share_token=None,
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        report_id = str(report.id)

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

    async with report_context.session_factory() as session:
        owner_report = Report(
            evaluation_id=int(owner_evaluation_id),
            summary="owner pdf report",
            metrics={},
            top_pros=[],
            top_cons=[],
            persona_segments={},
            pdf_url="/static/reports/owner.pdf",
            share_token=None,
        )
        other_report = Report(
            evaluation_id=int(other_evaluation_id),
            summary="other pdf report",
            metrics={},
            top_pros=[],
            top_cons=[],
            persona_segments={},
            pdf_url="/static/reports/other.pdf",
            share_token=None,
        )
        session.add_all([owner_report, other_report])
        await session.commit()
        await session.refresh(owner_report)
        await session.refresh(other_report)
        owner_report_id = str(owner_report.id)
        other_report_id = str(other_report.id)

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
