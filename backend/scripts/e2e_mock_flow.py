"""E2E mock flow script — runs the full MVP flow against a live server.

Usage:
    # Start the server first:
    uv run uvicorn app.main:app --reload

    # Then run:
    uv run python scripts/e2e_mock_flow.py

Set API_BASE_URL to override the default http://127.0.0.1:8000.
"""

from __future__ import annotations

import json
import os
import sys

import httpx


def main() -> None:
    base = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

    try:
        httpx.get(f"{base}/health", timeout=3)
    except httpx.ConnectError:
        print(
            f"ERROR: Cannot connect to {base}. "
            "Please start the server first:\n"
            "  uv run uvicorn app.main:app --reload",
            file=sys.stderr,
        )
        sys.exit(1)

    def p(step: str, key: str, value: object) -> None:
        print(f"  [{step}] {key} = {value}")

    # 1. Login
    print("\n=== 1. Login ===")
    resp = httpx.post(f"{base}/api/v1/auth/wechat/login", json={"code": "e2e_demo_user"})
    resp.raise_for_status()
    token = resp.json()["token"]
    user_id = resp.json().get("user", {}).get("id", "unknown")
    p("login", "user_id", user_id)
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Update profile
    print("\n=== 2. Update profile ===")
    resp = httpx.patch(
        f"{base}/api/v1/auth/profile",
        headers=headers,
        json={"role_type": "manufacturer", "nickname": "E2E品牌方"},
    )
    resp.raise_for_status()
    p("profile", "role_type", resp.json()["role_type"])

    # 3. Upload URL
    print("\n=== 3. Upload URL ===")
    resp = httpx.post(
        f"{base}/api/v1/products/upload-url",
        headers=headers,
        json={"filename": "front.jpg", "mime_type": "image/jpeg", "size_bytes": 2048},
    )
    resp.raise_for_status()
    object_key = resp.json()["object_key"]
    p("upload", "object_key", object_key)

    # 4. Create product
    print("\n=== 4. Create product ===")
    resp = httpx.post(
        f"{base}/api/v1/products",
        headers=headers,
        json={
            "name": "E2E演示面霜",
            "description": "温和保湿面霜，添加烟酰胺和神经酰胺。",
            "image_object_keys": [object_key],
        },
    )
    resp.raise_for_status()
    product_id = resp.json()["id"]
    p("product", "product_id", product_id)

    # 5. Create evaluation
    print("\n=== 5. Create evaluation ===")
    resp = httpx.post(
        f"{base}/api/v1/evaluations",
        headers=headers,
        json={"product_id": product_id},
    )
    resp.raise_for_status()
    evaluation_id = resp.json()["id"]
    p("evaluation", "evaluation_id", evaluation_id)

    # 6. Generate survey
    print("\n=== 6. Generate survey ===")
    resp = httpx.post(
        f"{base}/api/v1/surveys/generate",
        headers=headers,
        json={"product_id": product_id, "evaluation_id": evaluation_id},
    )
    resp.raise_for_status()
    survey_id = resp.json()["id"]
    q_count = len(resp.json()["questions"])
    p("survey", "survey_id", survey_id)
    p("survey", "question_count", q_count)

    # 7. Recommend personas
    print("\n=== 7. Recommend personas ===")
    resp = httpx.get(
        f"{base}/api/v1/personas/recommend?product_id={product_id}&count=20",
        headers=headers,
    )
    resp.raise_for_status()
    personas = resp.json()["items"]
    persona_ids = [str(pe["id"]) for pe in personas[:3]]
    p("recommend", "persona_count", len(personas))
    p("recommend", "selected_persona_ids", persona_ids)

    if not persona_ids:
        print("ERROR: No personas available. Run seed_personas.py first.", file=sys.stderr)
        sys.exit(1)

    # 8. Select personas
    print("\n=== 8. Select personas ===")
    resp = httpx.put(
        f"{base}/api/v1/evaluations/{evaluation_id}/personas",
        headers=headers,
        json={"persona_ids": persona_ids},
    )
    resp.raise_for_status()
    p("select", "status", "ok")

    # 9. Run evaluation
    print("\n=== 9. Run evaluation ===")
    resp = httpx.post(
        f"{base}/api/v1/evaluations/{evaluation_id}/run",
        headers=headers,
    )
    resp.raise_for_status()
    p("run", "status", resp.json()["status"])
    p("run", "progress", resp.json()["progress"])

    # 10. Get evaluation
    print("\n=== 10. Get evaluation ===")
    resp = httpx.get(f"{base}/api/v1/evaluations/{evaluation_id}", headers=headers)
    resp.raise_for_status()
    p("evaluation", "status", resp.json()["status"])

    # 11. Get answers
    print("\n=== 11. Get answers ===")
    resp = httpx.get(f"{base}/api/v1/evaluations/{evaluation_id}/answers", headers=headers)
    resp.raise_for_status()
    p("answers", "count", len(resp.json()))

    # 12. Get report
    print("\n=== 12. Get report ===")
    resp = httpx.get(f"{base}/api/v1/reports/by-evaluation/{evaluation_id}", headers=headers)
    resp.raise_for_status()
    report = resp.json()
    report_id = report["id"]
    p("report", "report_id", report_id)
    p("report", "overall_intent_average", report["metrics"]["overall_intent"]["average"])

    # 13. Create conversation
    print("\n=== 13. Create conversation ===")
    first_persona = persona_ids[0]
    resp = httpx.post(
        f"{base}/api/v1/conversations",
        headers=headers,
        json={"evaluation_id": evaluation_id, "persona_id": first_persona},
    )
    resp.raise_for_status()
    conversation_id = resp.json()["id"]
    p("conversation", "conversation_id", conversation_id)

    # 14. Send message (SSE)
    print("\n=== 14. Send message ===")
    resp = httpx.post(
        f"{base}/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
        json={"content": "你好，请问你对这款面霜怎么看？"},
    )
    resp.raise_for_status()
    sse_text = resp.text
    events = []
    for line in sse_text.strip().split("\n\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    event_types = [e["event"] for e in events]
    p("sse", "event_types", event_types)
    p("sse", "delta_count", event_types.count("delta"))

    # 15. Get messages
    print("\n=== 15. Get messages ===")
    resp = httpx.get(
        f"{base}/api/v1/conversations/{conversation_id}/messages",
        headers=headers,
    )
    resp.raise_for_status()
    msg_roles = [m["role"] for m in resp.json()["items"]]
    p("messages", "roles", msg_roles)

    print("\n" + "=" * 40)
    print("E2E_MOCK_FLOW_OK")


if __name__ == "__main__":
    main()
