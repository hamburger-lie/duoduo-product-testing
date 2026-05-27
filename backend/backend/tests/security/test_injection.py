"""Security tests: SQL injection, XSS, and input sanitization.

Dynamic penetration testing (DAST) — sends malicious payloads through
real HTTP requests and verifies the system rejects or neutralizes them.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.api.conftest import login

# Common SQL injection payloads
SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE users; --",
    "1' OR '1'='1",
    "1; SELECT * FROM users --",
    "' UNION SELECT null, null, null --",
    "admin'--",
    "1' AND 1=CAST((SELECT version()) AS int)--",
]

# XSS payloads
XSS_PAYLOADS = [
    '<script>alert("xss")</script>',
    '<img src=x onerror=alert(1)>',
    '"><svg onload=alert(1)>',
    "javascript:alert(1)",
    '<iframe src="javascript:alert(1)">',
]


class TestSQLInjection:
    """Verify SQL injection payloads are handled safely."""

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    async def test_product_name_injection(
        self, api_client: AsyncClient, payload: str,
    ) -> None:
        headers = await login(api_client, "sqli_test")
        resp = await api_client.post(
            "/api/v1/products",
            json={
                "name": payload,
                "description": "SQL注入测试产品，验证参数化查询是否有效防护。",
                "image_object_keys": ["test.jpg"],
            },
            headers=headers,
        )
        # Should either succeed (stored safely) or reject — never 500
        assert resp.status_code != 500

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    async def test_login_code_injection(
        self, api_client: AsyncClient, payload: str,
    ) -> None:
        resp = await api_client.post(
            "/api/v1/auth/wechat/login",
            json={"code": payload},
        )
        # Should handle safely
        assert resp.status_code in {200, 400, 422}

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    async def test_query_param_injection(
        self, api_client: AsyncClient, payload: str,
    ) -> None:
        headers = await login(api_client, "sqli_query_test")
        resp = await api_client.get(
            f"/api/v1/products?cursor={payload}",
            headers=headers,
        )
        assert resp.status_code != 500


class TestXSSProtection:
    """Verify XSS payloads are stored/returned safely."""

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    async def test_product_description_xss(
        self, api_client: AsyncClient, payload: str,
    ) -> None:
        headers = await login(api_client, "xss_test")
        resp = await api_client.post(
            "/api/v1/products",
            json={
                "name": "XSS Test",
                "description": payload + " 补充足够长度的描述文字来通过最小长度验证。",
                "image_object_keys": ["test.jpg"],
            },
            headers=headers,
        )
        # API is JSON-only, XSS is a client concern, but should never 500
        assert resp.status_code != 500

    @pytest.mark.parametrize("payload", XSS_PAYLOADS)
    async def test_persona_name_xss(
        self, api_client: AsyncClient, payload: str,
    ) -> None:
        headers = await login(api_client, "xss_persona_test")
        resp = await api_client.post(
            "/api/v1/personas",
            json={
                "name": payload,
                "age": 25,
                "gender": "female",
                "city": "北京",
                "occupation": "测试",
            },
            headers=headers,
        )
        assert resp.status_code != 500


class TestAuthorizationBypass:
    """Verify authorization boundaries cannot be bypassed."""

    async def test_access_other_user_product_by_id(
        self, api_client: AsyncClient,
    ) -> None:
        headers_a = await login(api_client, "authz_user_a")
        headers_b = await login(api_client, "authz_user_b")

        resp = await api_client.post(
            "/api/v1/products",
            json={
                "name": "Private Product",
                "description": "这个产品属于用户A，用户B不应该能够访问。",
                "image_object_keys": ["test.jpg"],
            },
            headers=headers_a,
        )
        product_id = resp.json()["id"]

        # User B tries to access
        resp = await api_client.get(
            f"/api/v1/products/{product_id}", headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_access_other_user_evaluation(
        self, api_client: AsyncClient,
    ) -> None:
        headers_a = await login(api_client, "authz_eval_a")
        headers_b = await login(api_client, "authz_eval_b")

        resp = await api_client.post(
            "/api/v1/products",
            json={
                "name": "Eval Auth Test",
                "description": "验证评估的跨用户访问控制是否正确实施。",
                "image_object_keys": ["test.jpg"],
            },
            headers=headers_a,
        )
        product_id = resp.json()["id"]

        resp = await api_client.post(
            "/api/v1/evaluations",
            json={"product_id": product_id},
            headers=headers_a,
        )
        eval_id = resp.json()["id"]

        # User B tries to access A's evaluation
        resp = await api_client.get(
            f"/api/v1/evaluations/{eval_id}", headers=headers_b,
        )
        assert resp.status_code == 404

    async def test_run_other_user_evaluation(
        self, api_client: AsyncClient,
    ) -> None:
        headers_a = await login(api_client, "authz_run_a")
        headers_b = await login(api_client, "authz_run_b")

        resp = await api_client.post(
            "/api/v1/products",
            json={
                "name": "Run Auth Test",
                "description": "验证不能运行其他用户的评估任务。",
                "image_object_keys": ["test.jpg"],
            },
            headers=headers_a,
        )
        product_id = resp.json()["id"]

        resp = await api_client.post(
            "/api/v1/evaluations",
            json={"product_id": product_id},
            headers=headers_a,
        )
        eval_id = resp.json()["id"]

        # User B tries to run A's evaluation
        resp = await api_client.post(
            f"/api/v1/evaluations/{eval_id}/run", headers=headers_b,
        )
        assert resp.status_code in {403, 404}

    async def test_manipulate_jwt_payload(
        self, api_client: AsyncClient,
    ) -> None:
        """Tampered JWT should be rejected."""
        import base64
        import json

        headers_a = await login(api_client, "jwt_tamper_user")
        token = headers_a["Authorization"].split(" ")[1]

        # Tamper with the payload
        parts = token.split(".")
        if len(parts) == 3:
            payload = json.loads(
                base64.urlsafe_b64decode(parts[1] + "==").decode()
            )
            payload["sub"] = "999999"  # Try to become another user
            tampered_payload = base64.urlsafe_b64encode(
                json.dumps(payload).encode()
            ).decode().rstrip("=")
            tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"

            resp = await api_client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {tampered_token}"},
            )
            assert resp.status_code == 401


class TestContentModeration:
    """Verify content moderation catches blocked content."""

    BLOCKED_INPUTS = [
        "这个产品含有毒品成分",
        "购买枪支的方式",
        "赌博技巧分享",
    ]

    @pytest.mark.parametrize("text", BLOCKED_INPUTS)
    async def test_product_description_moderation(
        self, api_client: AsyncClient, text: str,
    ) -> None:
        headers = await login(api_client, "moderation_test")
        resp = await api_client.post(
            "/api/v1/products",
            json={
                "name": "审核测试",
                "description": text + " 补充额外文字确保通过长度校验。",
                "image_object_keys": ["test.jpg"],
            },
            headers=headers,
        )
        assert resp.status_code in {400, 451}  # 451 = Unavailable For Legal Reasons
        assert "CONTENT_BLOCKED" in resp.json()["code"]  # AI_CONTENT_BLOCKED
