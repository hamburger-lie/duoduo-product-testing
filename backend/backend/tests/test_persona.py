from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.db.models.persona import Persona
from app.db.models.product import Product
from app.db.models.user import User
from app.main import app


@dataclass
class PersonaTestContext:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


PROFILE = {
    "bio": "关注护肤成分和真实使用感。",
    "shopping_habits": "先看评价再下单。",
    "skincare_concerns": ["暗沉", "屏障"],
    "brand_preferences": ["珀莱雅"],
    "price_sensitivity": "中等",
    "info_channels": ["小红书"],
    "decision_style": "理性比较",
    "pet_phrases": ["性价比怎么样"],
    "pain_points": ["怕营销夸大"],
    "lifestyle": "工作忙，护肤精简。",
}


@pytest.fixture
async def persona_context() -> AsyncIterator[PersonaTestContext]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(Product.__table__.create)
        await connection.run_sync(Persona.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        context = PersonaTestContext(client=client, session_factory=session_factory)
        await seed_system_personas(context)
        yield context

    app.dependency_overrides.clear()
    await engine.dispose()


async def seed_system_personas(context: PersonaTestContext) -> None:
    async with context.session_factory() as session:
        session.add_all(
            [
                build_persona(name="林雪", categories=["美妆", "护肤"], is_critical=True),
                build_persona(name="陈婷婷", categories=["美妆"], is_critical=True),
                build_persona(name="周曼", categories=["彩妆"], is_critical=False),
            ]
        )
        await session.commit()


def build_persona(
    *,
    name: str,
    categories: list[str],
    owner_id: int | None = None,
    is_critical: bool = False,
) -> Persona:
    return Persona(
        owner_id=owner_id,
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
        persona_tag=f"{name} 标签",
        profile=PROFILE,
        categories=categories,
        is_critical=is_critical,
        version=1,
        status="active",
    )


async def login(context: PersonaTestContext, code: str) -> tuple[str, str]:
    response = await context.client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    body = response.json()
    return str(body["token"]), str(body["user"]["id"])


def private_persona_payload(name: str = "张美丽") -> dict[str, object]:
    return {
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
        "profile": PROFILE,
        "ocean": {"o": 50, "c": 60, "e": 70, "a": 65, "n": 50},
    }


async def create_private_persona(
    context: PersonaTestContext,
    token: str,
    name: str = "张美丽",
) -> dict[str, object]:
    response = await context.client.post(
        "/api/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
        json=private_persona_payload(name),
    )
    assert response.status_code == 200
    return response.json()


async def create_product(context: PersonaTestContext, token: str) -> str:
    response = await context.client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "测评面霜",
            "description": "添加烟酰胺和神经酰胺，主打温和修护和提亮，适合日常护肤使用。",
            "image_object_keys": ["products/2026/05/123_front.jpg"],
        },
    )
    assert response.status_code == 200
    return str(response.json()["id"])


async def test_list_personas_returns_system_roles(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_list")
    response = await persona_context.client.get(
        "/api/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 3
    assert all(item["is_system"] for item in response.json()["items"])


async def test_list_personas_owner_scope_system(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_scope_system")
    await create_private_persona(persona_context, token)
    response = await persona_context.client.get(
        "/api/v1/personas?owner_scope=system",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 3


async def test_list_personas_owner_scope_mine(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_scope_mine")
    private_persona = await create_private_persona(persona_context, token)
    response = await persona_context.client.get(
        "/api/v1/personas?owner_scope=mine",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [private_persona["id"]]


async def test_list_personas_owner_scope_all(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_scope_all")
    await create_private_persona(persona_context, token)
    response = await persona_context.client.get(
        "/api/v1/personas?owner_scope=all",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 4


async def test_list_personas_category_filter(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_category")
    response = await persona_context.client.get(
        "/api/v1/personas?category=彩妆",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["name"] == "周曼"


async def test_list_personas_keyword_search(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_keyword")
    response = await persona_context.client.get(
        "/api/v1/personas?keyword=林雪",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_list_personas_excludes_critical_when_requested(
    persona_context: PersonaTestContext,
) -> None:
    token, _ = await login(persona_context, "mock_persona_critical")
    response = await persona_context.client.get(
        "/api/v1/personas?include_critical=false",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert all(not item["is_critical"] for item in response.json()["items"])


async def test_get_system_persona_detail_success(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_detail_system")
    list_response = await persona_context.client.get(
        "/api/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
    )
    persona_id = list_response.json()["items"][0]["id"]

    response = await persona_context.client.get(
        f"/api/v1/personas/{persona_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == persona_id
    assert response.json()["ocean"]["o"] == 70
    assert response.json()["profile"]["bio"]


async def test_create_private_persona_success(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_create")
    persona = await create_private_persona(persona_context, token)

    assert persona["id"].isdigit()
    assert persona["is_system"] is False
    assert persona["ocean"] == {"o": 50, "c": 60, "e": 70, "a": 65, "n": 50}


async def test_get_own_private_persona_success(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_get_private")
    persona = await create_private_persona(persona_context, token)
    response = await persona_context.client.get(
        f"/api/v1/personas/{persona['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == persona["id"]


async def test_update_own_private_persona_success(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_update_private")
    persona = await create_private_persona(persona_context, token)
    payload = private_persona_payload("张更新")
    response = await persona_context.client.patch(
        f"/api/v1/personas/{persona['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "张更新"


async def test_delete_own_private_persona_success(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_delete_private")
    persona = await create_private_persona(persona_context, token)
    response = await persona_context.client.delete(
        f"/api/v1/personas/{persona['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 204
    list_response = await persona_context.client.get(
        "/api/v1/personas?owner_scope=mine",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_response.json()["total"] == 0


async def test_cannot_update_system_persona(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_update_system")
    list_response = await persona_context.client.get(
        "/api/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
    )
    persona_id = list_response.json()["items"][0]["id"]
    response = await persona_context.client.patch(
        f"/api/v1/personas/{persona_id}",
        headers={"Authorization": f"Bearer {token}"},
        json=private_persona_payload("不能改系统"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERSONA_NOT_OWNED"


async def test_cannot_delete_system_persona(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_delete_system")
    list_response = await persona_context.client.get(
        "/api/v1/personas",
        headers={"Authorization": f"Bearer {token}"},
    )
    persona_id = list_response.json()["items"][0]["id"]
    response = await persona_context.client.delete(
        f"/api/v1/personas/{persona_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERSONA_NOT_OWNED"


async def test_user_cannot_access_other_users_private_persona(
    persona_context: PersonaTestContext,
) -> None:
    owner_token, _ = await login(persona_context, "mock_persona_owner")
    other_token, _ = await login(persona_context, "mock_persona_other")
    persona = await create_private_persona(persona_context, owner_token)

    get_response = await persona_context.client.get(
        f"/api/v1/personas/{persona['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    patch_response = await persona_context.client.patch(
        f"/api/v1/personas/{persona['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
        json=private_persona_payload("越权修改"),
    )
    delete_response = await persona_context.client.delete(
        f"/api/v1/personas/{persona['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert get_response.status_code == 404
    assert patch_response.status_code == 403
    assert delete_response.status_code == 403


async def test_recommend_personas_success(persona_context: PersonaTestContext) -> None:
    token, _ = await login(persona_context, "mock_persona_recommend")
    product_id = await create_product(persona_context, token)

    response = await persona_context.client.get(
        f"/api/v1/personas/recommend?product_id={product_id}&count=3",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["total"] >= 2
    assert any(item["is_critical"] for item in response.json()["items"])


async def test_recommend_personas_missing_product_fails(
    persona_context: PersonaTestContext,
) -> None:
    token, _ = await login(persona_context, "mock_persona_recommend_missing")
    response = await persona_context.client.get(
        "/api/v1/personas/recommend?product_id=999999&count=3",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_persona_endpoint_without_token_fails(persona_context: PersonaTestContext) -> None:
    response = await persona_context.client.get("/api/v1/personas")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


async def test_recommend_route_is_not_captured_by_persona_id(
    persona_context: PersonaTestContext,
) -> None:
    token, _ = await login(persona_context, "mock_persona_route_order")
    response = await persona_context.client.get(
        "/api/v1/personas/recommend?product_id=999999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_persona_paths_are_visible_in_openapi(
    persona_context: PersonaTestContext,
) -> None:
    response = await persona_context.client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/personas" in paths
    assert "/api/v1/personas/recommend" in paths
    assert "/api/v1/personas/{persona_id}" in paths
