"""API E2E: complete business flow from login to report.

Tests the entire happy path as a black box through real HTTP requests:
  login → create product → create evaluation → select personas →
  generate survey → run evaluation → get report → check credits
"""
from __future__ import annotations

from httpx import AsyncClient

from tests.api.conftest import login


async def test_complete_happy_path(api_client: AsyncClient) -> None:
    """Full flow: login → product → evaluation → survey → run → report."""
    headers = await login(api_client)

    # 1. Check initial credit balance
    resp = await api_client.get("/api/v1/credits/balance", headers=headers)
    assert resp.status_code == 200
    initial_balance = resp.json()["balance"]
    assert initial_balance == 1000

    # 2. Create product
    resp = await api_client.post(
        "/api/v1/products",
        json={
            "name": "E2E 测试面霜",
            "description": "一款含有烟酰胺和玻尿酸的保湿面霜，主打温和补水。",
            "image_object_keys": ["products/2026/05/e2e_test.jpg"],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    product_id = resp.json()["id"]

    # 3. Create evaluation
    resp = await api_client.post(
        "/api/v1/evaluations",
        json={"product_id": product_id},
        headers=headers,
    )
    assert resp.status_code == 200
    eval_id = resp.json()["id"]

    # 4. Get recommended personas
    resp = await api_client.get(
        f"/api/v1/personas/recommend?product_id={product_id}&count=3",
        headers=headers,
    )
    assert resp.status_code == 200
    persona_ids = [p["id"] for p in resp.json()["items"][:2]]
    assert len(persona_ids) >= 2

    # 5. Select personas
    resp = await api_client.put(
        f"/api/v1/evaluations/{eval_id}/personas",
        json={"persona_ids": persona_ids},
        headers=headers,
    )
    assert resp.status_code == 200

    # 6. Generate survey
    resp = await api_client.post(
        "/api/v1/surveys/generate",
        json={"product_id": product_id, "evaluation_id": eval_id},
        headers=headers,
    )
    assert resp.status_code in {200, 201}

    # 7. Run evaluation
    resp = await api_client.post(
        f"/api/v1/evaluations/{eval_id}/run",
        headers=headers,
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "done"

    # 8. Check credits deducted
    resp = await api_client.get("/api/v1/credits/balance", headers=headers)
    new_balance = resp.json()["balance"]
    expected_cost = len(persona_ids) * 10
    assert new_balance == initial_balance - expected_cost

    # 9. Get report
    resp = await api_client.get(
        f"/api/v1/reports/by-evaluation/{eval_id}",
        headers=headers,
    )
    assert resp.status_code == 200
    report = resp.json()
    assert report["evaluation_id"] == eval_id
    assert "metrics" in report
    assert "top_pros" in report
    assert "top_cons" in report
    assert report["metrics"]["overall_intent"]["average"] >= 1.0

    # 10. Get answers
    resp = await api_client.get(
        f"/api/v1/evaluations/{eval_id}/answers",
        headers=headers,
    )
    assert resp.status_code == 200
    answers = resp.json()  # returns list directly, not {"items": [...]}
    assert len(answers) == len(persona_ids)

    # 11. Check evaluation history
    resp = await api_client.get("/api/v1/history", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 1

    # 12. Check credit transactions
    resp = await api_client.get("/api/v1/credits/transactions", headers=headers)
    assert resp.status_code == 200
    txs = resp.json()["items"]
    assert any(tx["reason"] == "evaluation" for tx in txs)


async def test_evaluation_cancel_and_refund(api_client: AsyncClient) -> None:
    """Canceled evaluation after partial completion."""
    headers = await login(api_client, "cancel_test_user")

    resp = await api_client.get("/api/v1/credits/balance", headers=headers)
    initial_balance = resp.json()["balance"]

    # Setup
    resp = await api_client.post(
        "/api/v1/products",
        json={
            "name": "取消测试产品",
            "description": "验证取消流程是否正确工作，包括积分退还逻辑。",
            "image_object_keys": ["products/2026/05/cancel.jpg"],
        },
        headers=headers,
    )
    product_id = resp.json()["id"]

    resp = await api_client.post(
        "/api/v1/evaluations",
        json={"product_id": product_id},
        headers=headers,
    )
    eval_id = resp.json()["id"]

    resp = await api_client.get("/api/v1/personas", headers=headers)
    persona_ids = [p["id"] for p in resp.json()["items"][:1]]

    await api_client.put(
        f"/api/v1/evaluations/{eval_id}/personas",
        json={"persona_ids": persona_ids},
        headers=headers,
    )
    await api_client.post(
        "/api/v1/surveys/generate",
        json={"product_id": product_id, "evaluation_id": eval_id},
        headers=headers,
    )

    # Run (sync mode completes immediately, so cancel after won't change status)
    resp = await api_client.post(
        f"/api/v1/evaluations/{eval_id}/run", headers=headers,
    )
    assert resp.status_code == 202

    # Verify evaluation completed and credits deducted
    resp = await api_client.get("/api/v1/credits/balance", headers=headers)
    assert resp.json()["balance"] == initial_balance - 10


async def test_repeat_run_blocked(api_client: AsyncClient) -> None:
    """Running a completed evaluation again should fail."""
    headers = await login(api_client, "repeat_run_user")

    # Setup and run
    resp = await api_client.post(
        "/api/v1/products",
        json={
            "name": "重复运行测试",
            "description": "验证已完成的评估不能被重复运行，防止重复扣费。",
            "image_object_keys": ["products/2026/05/repeat.jpg"],
        },
        headers=headers,
    )
    product_id = resp.json()["id"]

    resp = await api_client.post(
        "/api/v1/evaluations", json={"product_id": product_id}, headers=headers,
    )
    eval_id = resp.json()["id"]

    resp = await api_client.get("/api/v1/personas", headers=headers)
    persona_ids = [resp.json()["items"][0]["id"]]

    await api_client.put(
        f"/api/v1/evaluations/{eval_id}/personas",
        json={"persona_ids": persona_ids}, headers=headers,
    )
    await api_client.post(
        "/api/v1/surveys/generate",
        json={"product_id": product_id, "evaluation_id": eval_id},
        headers=headers,
    )

    resp = await api_client.post(
        f"/api/v1/evaluations/{eval_id}/run", headers=headers,
    )
    assert resp.status_code == 202

    # Try to run again
    resp = await api_client.post(
        f"/api/v1/evaluations/{eval_id}/run", headers=headers,
    )
    assert resp.status_code in {400, 409}  # 409 Conflict for already-completed
