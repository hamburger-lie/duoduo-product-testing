from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.db.models.answer import Answer
from app.db.models.conversation import Conversation, ConversationMessage
from app.db.models.credit import CreditTransaction
from app.db.models.evaluation import Evaluation
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.report import Report
from app.db.models.survey import Survey
from app.db.models.user import User
from app.main import app


@dataclass
class PermissionContext:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


@pytest.fixture
async def permission_context() -> AsyncIterator[PermissionContext]:
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
        await connection.run_sync(Conversation.__table__.create)
        await connection.run_sync(ConversationMessage.__table__.create)
        await connection.run_sync(CreditTransaction.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield PermissionContext(client=client, session_factory=session_factory)

    app.dependency_overrides.clear()
    await engine.dispose()


async def login(context: PermissionContext, code: str) -> str:
    response = await context.client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return str(response.json()["token"])


async def user_id_for(context: PermissionContext, token: str) -> int:
    response = await context.client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    return int(response.json()["id"])


async def create_product(context: PermissionContext, token: str, name: str) -> str:
    response = await context.client.post(
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


async def create_private_persona(context: PermissionContext, token: str, name: str) -> str:
    response = await context.client.post(
        "/api/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "avatar": "person",
            "age": 35,
            "gender": "female",
            "city": "成都",
            "occupation": "全职妈妈",
            "income_monthly": 8000,
            "persona_tag": "性价比党",
            "categories": ["美妆"],
            "is_critical": False,
            "profile": {
                "bio": "重视性价比和真实口碑",
                "shopping_habits": "常在电商平台比价",
                "skincare_concerns": ["暗沉"],
                "brand_preferences": ["国货品牌"],
                "price_sensitivity": "高",
                "info_channels": ["小红书"],
                "decision_style": "看评价后决策",
                "pet_phrases": ["值不值这个价"],
                "pain_points": ["怕踩雷"],
                "lifestyle": "家庭场景为主",
            },
            "ocean": {"o": 50, "c": 60, "e": 70, "a": 65, "n": 50},
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def create_system_persona(context: PermissionContext, *, name: str = "林雪") -> str:
    async with context.session_factory() as session:
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
            persona_tag="成分党",
            profile={"bio": "关注成分"},
            categories=["美妆"],
            is_critical=False,
            version=1,
            status="active",
        )
        session.add(persona)
        await session.commit()
        return str(persona.id)


async def create_evaluation(context: PermissionContext, token: str, product_id: str) -> str:
    response = await context.client.post(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product_id},
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def generate_survey(
    context: PermissionContext,
    token: str,
    product_id: str,
    evaluation_id: str,
) -> str:
    response = await context.client.post(
        "/api/v1/surveys/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": product_id, "evaluation_id": evaluation_id},
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def prepare_done_evaluation(
    context: PermissionContext,
    token: str,
) -> tuple[str, str, str]:
    product_id = await create_product(context, token, "权限矩阵产品")
    evaluation_id = await create_evaluation(context, token, product_id)
    await generate_survey(context, token, product_id, evaluation_id)
    persona_id = await create_system_persona(context)

    select_response = await context.client.put(
        f"/api/v1/evaluations/{evaluation_id}/personas",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_ids": [persona_id]},
    )
    assert select_response.status_code == 200

    run_response = await context.client.post(
        f"/api/v1/evaluations/{evaluation_id}/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert run_response.status_code == 202
    assert run_response.json()["status"] == "done"
    return product_id, evaluation_id, persona_id


async def create_conversation(
    context: PermissionContext,
    token: str,
    evaluation_id: str,
    persona_id: str,
) -> str:
    response = await context.client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
        json={"evaluation_id": evaluation_id, "persona_id": persona_id},
    )
    assert response.status_code == 200
    return str(response.json()["id"])


def editable_questions() -> list[dict[str, object]]:
    return [
        {
            "id": "q1",
            "dim": "first_impression",
            "type": "scale_1_5",
            "question": "整体吸引力评分是多少？",
            "options": None,
        }
    ]


async def test_owner_can_access_own_resources(permission_context: PermissionContext) -> None:
    owner_token = await login(permission_context, "perm_owner_access")
    product_id, evaluation_id, persona_id = await prepare_done_evaluation(
        permission_context,
        owner_token,
    )
    private_persona_id = await create_private_persona(
        permission_context,
        owner_token,
        "我的私有角色",
    )
    survey_response = await permission_context.client.get(
        f"/api/v1/evaluations/{evaluation_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    survey_id = str(survey_response.json()["survey_id"])
    conversation_id = await create_conversation(
        permission_context,
        owner_token,
        evaluation_id,
        persona_id,
    )

    responses = [
        await permission_context.client.get(
            f"/api/v1/products/{product_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/personas/{private_persona_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/surveys/{survey_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/evaluations/{evaluation_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/reports/by-evaluation/{evaluation_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {owner_token}"},
        ),
        await permission_context.client.get(
            "/api/v1/credits/balance",
            headers={"Authorization": f"Bearer {owner_token}"},
        ),
        await permission_context.client.get(
            "/api/v1/history",
            headers={"Authorization": f"Bearer {owner_token}"},
        ),
    ]

    assert all(response.status_code == 200 for response in responses)


async def test_non_owner_cannot_access_other_user_details(
    permission_context: PermissionContext,
) -> None:
    owner_token = await login(permission_context, "perm_detail_owner")
    other_token = await login(permission_context, "perm_detail_other")
    product_id, evaluation_id, persona_id = await prepare_done_evaluation(
        permission_context,
        owner_token,
    )
    private_persona_id = await create_private_persona(
        permission_context,
        owner_token,
        "别人的私有角色",
    )
    survey_response = await permission_context.client.get(
        f"/api/v1/evaluations/{evaluation_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    survey_id = str(survey_response.json()["survey_id"])
    conversation_id = await create_conversation(
        permission_context,
        owner_token,
        evaluation_id,
        persona_id,
    )

    responses = [
        await permission_context.client.get(
            f"/api/v1/products/{product_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/personas/{private_persona_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/surveys/{survey_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/evaluations/{evaluation_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/reports/by-evaluation/{evaluation_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.get(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404, 404]


async def test_lists_do_not_leak_other_user_data(permission_context: PermissionContext) -> None:
    owner_token = await login(permission_context, "perm_list_owner")
    other_token = await login(permission_context, "perm_list_other")
    owner_product_id, owner_evaluation_id, owner_persona_id = await prepare_done_evaluation(
        permission_context,
        owner_token,
    )
    owner_private_persona_id = await create_private_persona(
        permission_context,
        owner_token,
        "我的角色",
    )
    await create_conversation(
        permission_context,
        owner_token,
        owner_evaluation_id,
        owner_persona_id,
    )

    other_product_id, other_evaluation_id, other_persona_id = await prepare_done_evaluation(
        permission_context,
        other_token,
    )
    other_private_persona_id = await create_private_persona(
        permission_context,
        other_token,
        "别人的角色",
    )
    await create_conversation(
        permission_context,
        other_token,
        other_evaluation_id,
        other_persona_id,
    )

    products = await permission_context.client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    personas = await permission_context.client.get(
        "/api/v1/personas?owner_scope=mine",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    evaluations = await permission_context.client.get(
        "/api/v1/evaluations",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    conversations = await permission_context.client.get(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    credits = await permission_context.client.get(
        "/api/v1/credits/transactions",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    history = await permission_context.client.get(
        "/api/v1/history",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert [item["id"] for item in products.json()["items"]] == [owner_product_id]
    assert [item["id"] for item in personas.json()["items"]] == [owner_private_persona_id]
    assert [item["id"] for item in evaluations.json()["items"]] == [owner_evaluation_id]
    assert [item["evaluation_id"] for item in conversations.json()["items"]] == [
        owner_evaluation_id
    ]
    assert credits.json()["items"] == []
    assert [item["evaluation_id"] for item in history.json()["items"]] == [owner_evaluation_id]
    assert other_product_id != owner_product_id
    assert other_private_persona_id != owner_private_persona_id
    assert other_evaluation_id != owner_evaluation_id


async def test_missing_resources_return_not_found(permission_context: PermissionContext) -> None:
    token = await login(permission_context, "perm_missing")

    responses = [
        await permission_context.client.get(
            "/api/v1/products/999999",
            headers={"Authorization": f"Bearer {token}"},
        ),
        await permission_context.client.get(
            "/api/v1/personas/999999",
            headers={"Authorization": f"Bearer {token}"},
        ),
        await permission_context.client.get(
            "/api/v1/surveys/999999",
            headers={"Authorization": f"Bearer {token}"},
        ),
        await permission_context.client.get(
            "/api/v1/evaluations/999999",
            headers={"Authorization": f"Bearer {token}"},
        ),
        await permission_context.client.get(
            "/api/v1/reports/by-evaluation/999999",
            headers={"Authorization": f"Bearer {token}"},
        ),
        await permission_context.client.get(
            "/api/v1/conversations/999999/messages",
            headers={"Authorization": f"Bearer {token}"},
        ),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404, 404, 404, 404]


async def test_non_owner_cannot_mutate_other_user_resources(
    permission_context: PermissionContext,
) -> None:
    owner_token = await login(permission_context, "perm_write_owner")
    other_token = await login(permission_context, "perm_write_other")
    product_id = await create_product(permission_context, owner_token, "别人的产品")
    evaluation_id = await create_evaluation(permission_context, owner_token, product_id)
    survey_id = await generate_survey(
        permission_context,
        owner_token,
        product_id,
        evaluation_id,
    )
    private_persona_id = await create_private_persona(
        permission_context,
        owner_token,
        "别人的私有角色",
    )
    system_persona_id = await create_system_persona(permission_context, name="周曼")
    _, done_evaluation_id, done_persona_id = await prepare_done_evaluation(
        permission_context,
        owner_token,
    )
    conversation_id = await create_conversation(
        permission_context,
        owner_token,
        done_evaluation_id,
        done_persona_id,
    )

    responses = [
        await permission_context.client.post(
            f"/api/v1/products/{product_id}/reanalyze",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.patch(
            f"/api/v1/personas/{private_persona_id}",
            headers={"Authorization": f"Bearer {other_token}"},
            json={
                "name": "越权修改",
                "avatar": "person",
                "age": 35,
                "gender": "female",
                "city": "成都",
                "occupation": "全职妈妈",
                "income_monthly": 8000,
                "persona_tag": "性价比党",
                "categories": ["美妆"],
                "is_critical": False,
                "profile": {
                    "bio": "重视性价比和真实口碑",
                    "shopping_habits": "常在电商平台比价",
                    "skincare_concerns": ["暗沉"],
                    "brand_preferences": ["国货品牌"],
                    "price_sensitivity": "高",
                    "info_channels": ["小红书"],
                    "decision_style": "看评价后决策",
                    "pet_phrases": ["值不值这个价"],
                    "pain_points": ["怕踩雷"],
                    "lifestyle": "家庭场景为主",
                },
                "ocean": {"o": 50, "c": 60, "e": 70, "a": 65, "n": 50},
            },
        ),
        await permission_context.client.delete(
            f"/api/v1/personas/{private_persona_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.put(
            f"/api/v1/surveys/{survey_id}/questions",
            headers={"Authorization": f"Bearer {other_token}"},
            json=editable_questions(),
        ),
        await permission_context.client.put(
            f"/api/v1/evaluations/{evaluation_id}/personas",
            headers={"Authorization": f"Bearer {other_token}"},
            json={"persona_ids": [system_persona_id]},
        ),
        await permission_context.client.post(
            f"/api/v1/evaluations/{evaluation_id}/run",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.post(
            f"/api/v1/evaluations/{evaluation_id}/cancel",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
        await permission_context.client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        ),
    ]

    assert [response.status_code for response in responses] == [
        404,
        403,
        403,
        404,
        404,
        404,
        404,
        404,
    ]
