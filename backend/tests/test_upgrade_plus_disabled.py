from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def test_plus_order_route_returns_404_when_payment_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_PAYMENT_ENABLED", "false")

    response = TestClient(app).post("/api/v1/upgrade/plus/order")

    assert response.status_code == 404


def test_plus_orders_route_returns_404_when_payment_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_PAYMENT_ENABLED", "false")

    response = TestClient(app).get("/api/v1/upgrade/plus/orders")

    assert response.status_code == 404


def test_plus_notify_route_returns_404_when_payment_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLUS_PAYMENT_ENABLED", "false")

    response = TestClient(app).post(
        "/api/v1/upgrade/plus/notify",
        json={"event_type": "TRANSACTION.SUCCESS", "resource": {}},
    )

    assert response.status_code == 404
