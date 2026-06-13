from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.routers import persona as persona_router
from app.routers import product as product_router
from app.schemas.persona import PersonaPageResponse
from app.schemas.product import ProductAiSummary, ProductListResponse, ProductResponse


class _FakeCache:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.get = AsyncMock(return_value=(False, None))
        self.set = AsyncMock()
        self.delete_pattern = AsyncMock()


def _user(user_id: int = 42) -> SimpleNamespace:
    return SimpleNamespace(id=user_id)


def _persona_payload() -> dict[str, object]:
    return {
        "items": [
            {
                "id": "1",
                "name": "林雪",
                "avatar": "person",
                "age": 28,
                "gender": "female",
                "city": "上海",
                "city_tier": 1,
                "occupation": "产品经理",
                "income_monthly": 25000,
                "persona_tag": "理性成分党",
                "categories": ["美妆"],
                "is_critical": True,
                "is_system": True,
            }
        ],
        "page": 1,
        "page_size": 20,
        "total": 1,
        "total_pages": 1,
    }


def _product_response(product_id: str = "9") -> ProductResponse:
    return ProductResponse(
        id=product_id,
        name="焕颜修护面霜",
        description="添加烟酰胺和神经酰胺，主打温和修护和提亮，适合日常护肤使用。",
        image_urls=["https://example.test/product.jpg"],
        category="美妆",
        sub_category="面霜",
        brand="测试品牌",
        price=Decimal("199.00"),
        price_range="100-200",
        target_channel="ec",
        ai_summary=ProductAiSummary(main_selling_points=["温和修护"]),
        status="ready",
        created_at="2026-06-08T00:00:00Z",
    )


def _product_payload() -> dict[str, object]:
    return ProductListResponse(
        items=[_product_response()],
        next_cursor=None,
        has_more=False,
    ).model_dump(mode="json")


async def test_list_personas_returns_cached_response_without_service_call(
    monkeypatch,
) -> None:
    cache = _FakeCache("personas")
    cache.get = AsyncMock(return_value=(True, _persona_payload()))
    service_list = AsyncMock()

    monkeypatch.setattr(persona_router, "persona_list_cache", cache)
    monkeypatch.setattr(
        persona_router.PersonaService,
        "list_personas",
        service_list,
    )

    response = await persona_router.list_personas(
        category=None,
        page=1,
        page_size=20,
        include_critical=True,
        owner_scope="all",
        keyword=None,
        current_user=_user(),
        session=object(),
    )

    assert isinstance(response, PersonaPageResponse)
    assert response.items[0].name == "林雪"
    service_list.assert_not_awaited()


async def test_list_products_returns_cached_response_without_service_call(
    monkeypatch,
) -> None:
    cache = _FakeCache("products")
    cache.get = AsyncMock(return_value=(True, _product_payload()))
    service_list = AsyncMock()

    monkeypatch.setattr(product_router, "product_list_cache", cache)
    monkeypatch.setattr(
        product_router.ProductService,
        "list_products",
        service_list,
    )

    response = await product_router.list_products(
        cursor=None,
        limit=20,
        current_user=_user(),
        session=object(),
    )

    assert isinstance(response, ProductListResponse)
    assert response.items[0].price == Decimal("199.00")
    service_list.assert_not_awaited()


async def test_list_products_caches_service_response_on_miss(monkeypatch) -> None:
    cache = _FakeCache("products")
    cache.get = AsyncMock(return_value=(False, None))
    service_response = ProductListResponse(
        items=[_product_response()],
        next_cursor=None,
        has_more=False,
    )
    service_list = AsyncMock(return_value=service_response)

    monkeypatch.setattr(product_router, "product_list_cache", cache)
    monkeypatch.setattr(
        product_router.ProductService,
        "list_products",
        service_list,
    )

    response = await product_router.list_products(
        cursor=None,
        limit=20,
        current_user=_user(),
        session=object(),
    )

    assert response == service_response
    service_list.assert_awaited_once()
    cache.set.assert_awaited_once()
    cached_payload = cache.set.await_args.args[1]
    assert cached_payload["items"][0]["price"] == "199.00"


async def test_create_product_invalidates_user_product_list_cache(monkeypatch) -> None:
    cache = _FakeCache("products")
    service_create = AsyncMock(return_value=_product_response())

    monkeypatch.setattr(product_router, "product_list_cache", cache)
    monkeypatch.setattr(
        product_router.ProductService,
        "create_product",
        service_create,
    )

    response = await product_router.create_product(
        payload=SimpleNamespace(),
        current_user=_user(77),
        session=object(),
    )

    assert response.id == "9"
    cache.delete_pattern.assert_awaited_once_with("user:77:*")


async def test_create_persona_invalidates_user_persona_list_cache(monkeypatch) -> None:
    cache = _FakeCache("personas")
    service_create = AsyncMock()

    monkeypatch.setattr(persona_router, "persona_list_cache", cache)
    monkeypatch.setattr(
        persona_router.PersonaService,
        "create_persona",
        service_create,
    )

    await persona_router.create_persona(
        payload=SimpleNamespace(),
        current_user=_user(88),
        session=object(),
    )

    cache.delete_pattern.assert_awaited_once_with("user:88:*")
