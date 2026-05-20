"""Locust load test for duoduo-product-testing API.

Usage:
    # Start the server first:
    docker compose up -d
    # or: uv run uvicorn app.main:app --port 8000

    # Run headless (CLI):
    uv run locust -f tests/performance/locustfile.py --headless \
        -u 50 -r 5 --run-time 2m \
        --host http://localhost:8000

    # Run with web UI:
    uv run locust -f tests/performance/locustfile.py --host http://localhost:8000
    # Open http://localhost:8089

Key metrics to watch:
    - RPS (requests per second)
    - P50/P95/P99 response times
    - Error rate (should be < 1%)
    - DB pool exhaustion (check /metrics)
"""
from __future__ import annotations

import random
import string

from locust import HttpUser, between, task


def _random_code() -> str:
    return "load_" + "".join(random.choices(string.ascii_lowercase, k=8))


class DuoduoUser(HttpUser):
    """Simulates a typical user session: login, browse, create, evaluate."""

    wait_time = between(1, 3)
    host = "http://localhost:8000"

    def on_start(self) -> None:
        """Login on user spawn."""
        resp = self.client.post(
            "/api/v1/auth/wechat/login",
            json={"code": _random_code()},
        )
        if resp.status_code == 200:
            token = resp.json().get("token", "")
            self.headers = {"Authorization": f"Bearer {token}"}
            self.product_id: str | None = None
            self.eval_id: str | None = None
        else:
            self.headers = {}

    @task(5)
    def health_check(self) -> None:
        """High-frequency health check (simulates LB probing)."""
        self.client.get("/health/live")

    @task(3)
    def list_personas(self) -> None:
        self.client.get("/api/v1/personas", headers=self.headers)

    @task(3)
    def get_balance(self) -> None:
        self.client.get("/api/v1/credits/balance", headers=self.headers)

    @task(2)
    def list_products(self) -> None:
        self.client.get("/api/v1/products", headers=self.headers)

    @task(2)
    def list_evaluations(self) -> None:
        self.client.get("/api/v1/evaluations", headers=self.headers)

    @task(2)
    def get_history(self) -> None:
        self.client.get("/api/v1/history", headers=self.headers)

    @task(1)
    def create_product(self) -> None:
        resp = self.client.post(
            "/api/v1/products",
            json={
                "name": f"Load Test Product {random.randint(1, 10000)}",
                "description": "压力测试创建的产品，验证高并发下产品创建接口的稳定性和性能表现。",
                "image_object_keys": ["products/loadtest/img.jpg"],
            },
            headers=self.headers,
        )
        if resp.status_code == 200:
            self.product_id = str(resp.json().get("id"))

    @task(1)
    def create_and_run_evaluation(self) -> None:
        """Full evaluation flow: create → personas → survey → run."""
        if not self.product_id:
            return

        # Create evaluation
        resp = self.client.post(
            "/api/v1/evaluations",
            json={"product_id": self.product_id},
            headers=self.headers,
        )
        if resp.status_code != 200:
            return
        eval_id = str(resp.json()["id"])

        # Get personas
        resp = self.client.get("/api/v1/personas", headers=self.headers)
        if resp.status_code != 200 or not resp.json().get("items"):
            return
        persona_ids = [resp.json()["items"][0]["id"]]

        # Select personas
        self.client.put(
            f"/api/v1/evaluations/{eval_id}/personas",
            json={"persona_ids": persona_ids},
            headers=self.headers,
        )

        # Generate survey
        self.client.post(
            "/api/v1/surveys/generate",
            json={"product_id": self.product_id, "evaluation_id": eval_id},
            headers=self.headers,
        )

        # Run evaluation
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
        self.client.get(
            f"/api/v1/reports/by-evaluation/{self.eval_id}",
            headers=self.headers,
        )

    @task(1)
    def get_metrics(self) -> None:
        """Scrape metrics endpoint (simulates Prometheus)."""
        self.client.get("/metrics")


class ReadOnlyUser(HttpUser):
    """Read-heavy user that only browses (simulates returning visitors)."""

    wait_time = between(0.5, 2)
    weight = 3  # 3x more likely to spawn than DuoduoUser

    def on_start(self) -> None:
        resp = self.client.post(
            "/api/v1/auth/wechat/login",
            json={"code": _random_code()},
        )
        if resp.status_code == 200:
            self.headers = {"Authorization": f"Bearer {resp.json()['token']}"}
        else:
            self.headers = {}

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

    @task(1)
    def get_credit_transactions(self) -> None:
        self.client.get("/api/v1/credits/transactions", headers=self.headers)
