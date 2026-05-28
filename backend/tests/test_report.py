from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

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


async def test_report_overall_intent_nps(report_context: ReportContext) -> None:
    token = await login(report_context, "report_nps")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    nps = response.json()["metrics"]["overall_intent"]["nps"]
    assert isinstance(nps, int)
    assert -100 <= nps <= 100


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


async def test_report_price_sensitivity_has_data(report_context: ReportContext) -> None:
    """价格敏感度应从答卷计算而非返回 mock 数据。"""

    token = await login(report_context, "report_price")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    ps = response.json()["metrics"]["price_sensitivity"]
    assert "median_acceptable_price" in ps
    assert isinstance(ps["median_acceptable_price"], (int, float))


async def test_report_summary_includes_dimension_insight(report_context: ReportContext) -> None:
    """摘要应包含维度亮点和短板信息。"""

    token = await login(report_context, "report_dim_summary")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    summary = response.json()["summary"]
    assert "角色" in summary
    assert "维度" in summary or "分" in summary


async def test_report_top_pros_title_contains_dimension(report_context: ReportContext) -> None:
    """亮点标题应包含维度名称而非通用文案。"""

    token = await login(report_context, "report_dim_pros")
    evaluation_id, _ = await prepare_done_evaluation(report_context, token=token)

    response = await report_context.client.get(
        f"/api/v1/reports/by-evaluation/{evaluation_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    top_pros = response.json()["top_pros"]
    assert len(top_pros) >= 1
    # 标题不应该是旧的通用文案
    assert top_pros[0]["title"] != "产品整体获得正面评价"
