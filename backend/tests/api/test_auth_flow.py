"""API E2E: authentication and authorization flows."""
from __future__ import annotations

from httpx import AsyncClient

from tests.api.conftest import login


async def test_login_returns_token_and_user(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/auth/wechat/login", json={"code": "auth_flow_user"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "token" in body
    assert "user" in body
    assert body["user"]["credit_balance"] == 1000


async def test_no_token_returns_401(api_client: AsyncClient) -> None:
    for endpoint in [
        "/api/v1/products",
        "/api/v1/evaluations",
        "/api/v1/personas",
        "/api/v1/credits/balance",
        "/api/v1/history",
    ]:
        resp = await api_client.get(endpoint)
        assert resp.status_code == 401, f"{endpoint} should require auth"
        assert resp.json()["code"] == "AUTH_REQUIRED"


async def test_invalid_token_returns_401(api_client: AsyncClient) -> None:
    headers = {"Authorization": "Bearer invalid.token.here"}
    resp = await api_client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401


async def test_logout_endpoint_succeeds(api_client: AsyncClient) -> None:
    """Logout endpoint returns 200. Token invalidation requires Redis (tested in integration)."""
    headers = await login(api_client, "logout_test_user")

    # Token works before logout
    resp = await api_client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200

    # Logout should succeed even without Redis
    resp = await api_client.post("/api/v1/auth/logout", headers=headers)
    assert resp.status_code == 200


async def test_cross_user_isolation(api_client: AsyncClient) -> None:
    """User A cannot access User B's resources."""
    headers_a = await login(api_client, "user_a")
    headers_b = await login(api_client, "user_b")

    # User A creates a product
    resp = await api_client.post(
        "/api/v1/products",
        json={
            "name": "隔离测试产品",
            "description": "验证用户之间的数据隔离，A 的产品 B 看不到。",
            "image_object_keys": ["products/test.jpg"],
        },
        headers=headers_a,
    )
    assert resp.status_code == 200
    product_id = resp.json()["id"]

    # User B cannot see User A's product
    resp = await api_client.get(
        f"/api/v1/products/{product_id}", headers=headers_b,
    )
    assert resp.status_code == 404

    # User B's product list should be empty
    resp = await api_client.get("/api/v1/products", headers=headers_b)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 0


async def test_token_refresh(api_client: AsyncClient) -> None:
    headers = await login(api_client, "refresh_test_user")
    resp = await api_client.post("/api/v1/auth/refresh", headers=headers)
    assert resp.status_code == 200
    assert "token" in resp.json()


async def test_empty_login_code_rejected(api_client: AsyncClient) -> None:
    resp = await api_client.post(
        "/api/v1/auth/wechat/login", json={"code": ""},
    )
    assert resp.status_code in {400, 422}
