"""Token-pool load test — bypasses login so we measure real request capacity.

Tokens are pre-generated (see scripts/gen_loadtest_tokens.py) and mounted at
/mnt/locust/tokens.json. Each simulated user grabs a distinct token on start,
so there is no per-IP login rate-limit cascade.

Run:
    docker run --rm --network soul-unified_default \
      -v "<host>/tests/performance:/mnt/locust" \
      locustio/locust -f /mnt/locust/locustfile_tokens.py --headless \
      -u 200 -r 20 --run-time 3m --host http://duoduo-api:8000
"""
from __future__ import annotations

import itertools
import json
import random
import threading

from locust import HttpUser, between, task

# Load the pre-generated token pool once per locust process.
with open("/mnt/locust/tokens.json", encoding="utf-8") as _f:
    _TOKENS: list[str] = json.load(_f)

_token_cycle = itertools.cycle(_TOKENS)
_lock = threading.Lock()


def _next_token() -> str:
    with _lock:
        return next(_token_cycle)


class TokenUser(HttpUser):
    """Authenticated user using a pre-issued token (no login call)."""

    wait_time = between(1, 3)

    def on_start(self) -> None:
        token = _next_token()
        self.headers = {"Authorization": f"Bearer {token}"}
        self.product_id: str | None = None
        self.eval_id: str | None = None

    # ---- read-heavy traffic ----
    @task(5)
    def list_personas(self) -> None:
        self.client.get("/api/v1/personas", headers=self.headers)

    @task(3)
    def get_balance(self) -> None:
        self.client.get("/api/v1/credits/balance", headers=self.headers)

    @task(3)
    def list_products(self) -> None:
        self.client.get("/api/v1/products", headers=self.headers)

    @task(2)
    def list_evaluations(self) -> None:
        self.client.get("/api/v1/evaluations", headers=self.headers)

    @task(2)
    def get_history(self) -> None:
        self.client.get("/api/v1/history", headers=self.headers)

    @task(1)
    def health(self) -> None:
        self.client.get("/health/live")

    # ---- write traffic ----
    @task(1)
    def create_product(self) -> None:
        resp = self.client.post(
            "/api/v1/products",
            json={
                "name": f"Load Test Product {random.randint(1, 100000)}",
                "description": "压力测试创建的产品，用于验证高并发下产品创建接口的稳定性。",
                "image_object_keys": ["products/loadtest/img.jpg"],
            },
            headers=self.headers,
        )
        if resp.status_code == 200:
            self.product_id = str(resp.json().get("id"))

    @task(1)
    def create_and_run_evaluation(self) -> None:
        """Full mock-AI evaluation flow: create → personas → survey → run."""
        if not self.product_id:
            return
        resp = self.client.post(
            "/api/v1/evaluations",
            json={"product_id": self.product_id},
            headers=self.headers,
        )
        if resp.status_code != 200:
            return
        eval_id = str(resp.json()["id"])

        resp = self.client.get("/api/v1/personas", headers=self.headers)
        if resp.status_code != 200 or not resp.json().get("items"):
            return
        persona_ids = [resp.json()["items"][0]["id"]]

        self.client.put(
            f"/api/v1/evaluations/{eval_id}/personas",
            json={"persona_ids": persona_ids},
            headers=self.headers,
        )
        self.client.post(
            "/api/v1/surveys/generate",
            json={"product_id": self.product_id, "evaluation_id": eval_id},
            headers=self.headers,
        )
        resp = self.client.post(
            f"/api/v1/evaluations/{eval_id}/run",
            headers=self.headers,
        )
        if resp.status_code == 202:
            self.eval_id = eval_id

    @task(1)
    def get_report(self) -> None:
        if not self.eval_id:
            return
        with self.client.get(
            f"/api/v1/reports/by-evaluation/{self.eval_id}",
            headers=self.headers,
            catch_response=True,
        ) as resp:
            if resp.status_code in {400, 404}:
                resp.success()
