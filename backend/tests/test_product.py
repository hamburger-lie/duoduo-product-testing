from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.deps import get_db_session
from app.db.models.product import Product
from app.db.models.user import User
from app.main import app


@pytest.fixture
async def product_client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(User.__table__.create)
        await connection.run_sync(Product.__table__.create)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


async def login(client: AsyncClient, code: str) -> str:
    response = await client.post("/api/v1/auth/wechat/login", json={"code": code})
    assert response.status_code == 200
    return str(response.json()["token"])


async def create_product(
    client: AsyncClient,
    token: str,
    name: str = "焕颜修护面霜",
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "description": "添加烟酰胺和神经酰胺，主打温和修护和提亮，适合日常护肤使用。",
            "image_object_keys": ["products/2026/05/123_front.jpg"],
            "brand": "测试品牌",
            "price": "199.00",
            "target_channel": "ec",
        },
    )
    assert response.status_code == 200
    return response.json()


async def test_upload_url_success(product_client: AsyncClient) -> None:
    token = await login(product_client, "mock_product_upload")
    response = await product_client.post(
        "/api/v1/products/upload-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "front.jpg", "mime_type": "image/jpeg", "size_bytes": 1024},
    )

    assert response.status_code == 200
    assert response.json()["method"] == "PUT"
    assert response.json()["headers"] == {"Content-Type": "image/jpeg"}
    assert response.json()["object_key"].startswith("products/")
    assert response.json()["expires_in"] == 600


async def test_upload_url_invalid_file_type(product_client: AsyncClient) -> None:
    token = await login(product_client, "mock_product_bad_type")
    response = await product_client.post(
        "/api/v1/products/upload-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "front.gif", "mime_type": "image/gif", "size_bytes": 1024},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_FILE_TYPE"


async def test_upload_url_file_too_large(product_client: AsyncClient) -> None:
    token = await login(product_client, "mock_product_large")
    response = await product_client.post(
        "/api/v1/products/upload-url",
        headers={"Authorization": f"Bearer {token}"},
        json={"filename": "front.png", "mime_type": "image/png", "size_bytes": 5 * 1024 * 1024 + 1},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "FILE_TOO_LARGE"


async def test_create_product_success(product_client: AsyncClient) -> None:
    token = await login(product_client, "mock_product_create")
    product = await create_product(product_client, token)

    assert product["id"].isdigit()
    assert product["status"] == "ready"
    assert product["ai_summary"]["main_selling_points"]
    assert product["ai_summary"]["key_ingredients"]


async def test_create_product_short_description_validation(product_client: AsyncClient) -> None:
    token = await login(product_client, "mock_product_short")
    response = await product_client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={"description": "太短", "image_object_keys": ["products/2026/05/1.jpg"]},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_create_product_image_count_validation(product_client: AsyncClient) -> None:
    token = await login(product_client, "mock_product_images")
    response = await product_client.post(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "description": "这是一个长度足够的产品描述，用于测试图片数量校验。",
            "image_object_keys": [],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


async def test_get_product_detail_success(product_client: AsyncClient) -> None:
    token = await login(product_client, "mock_product_detail")
    product = await create_product(product_client, token)
    response = await product_client.get(
        f"/api/v1/products/{product['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == product["id"]


async def test_get_other_users_product_returns_not_found(product_client: AsyncClient) -> None:
    owner_token = await login(product_client, "mock_product_owner")
    other_token = await login(product_client, "mock_product_other")
    product = await create_product(product_client, owner_token)

    response = await product_client.get(
        f"/api/v1/products/{product['id']}",
        headers={"Authorization": f"Bearer {other_token}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "PRODUCT_NOT_FOUND"


async def test_product_list_only_returns_current_users_products(
    product_client: AsyncClient,
) -> None:
    owner_token = await login(product_client, "mock_product_list_owner")
    other_token = await login(product_client, "mock_product_list_other")
    own_product = await create_product(product_client, owner_token, name="自己的产品")
    await create_product(product_client, other_token, name="别人的产品")

    response = await product_client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [own_product["id"]]
    assert response.json()["has_more"] is False


async def test_reanalyze_product_success(product_client: AsyncClient) -> None:
    token = await login(product_client, "mock_product_reanalyze")
    product = await create_product(product_client, token)
    response = await product_client.post(
        f"/api/v1/products/{product['id']}/reanalyze",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == product["id"]
    assert response.json()["ai_summary"]["competitive_position"]


async def test_product_endpoint_without_token_fails(product_client: AsyncClient) -> None:
    response = await product_client.get("/api/v1/products")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


async def test_product_endpoints_are_visible_in_openapi(product_client: AsyncClient) -> None:
    response = await product_client.get("/openapi.json")

    paths = response.json()["paths"]
    assert "/api/v1/products/upload-url" in paths
    assert "/api/v1/products" in paths
    assert "/api/v1/products/{product_id}" in paths
    assert "/api/v1/products/{product_id}/reanalyze" in paths
