from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.core import exceptions


async def test_db_pool_timeout_returns_service_busy_response() -> None:
    app = FastAPI()
    app.exception_handler(SQLAlchemyTimeoutError)(
        exceptions.db_pool_timeout_exception_handler
    )
    app.exception_handler(Exception)(exceptions.unhandled_exception_handler)

    @app.get("/boom")
    async def boom() -> None:
        raise SQLAlchemyTimeoutError("pool exhausted")

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "2"
    assert response.json()["code"] == "SERVICE_BUSY"
    assert response.json()["message"] == "系统繁忙，请稍后再试"


async def test_exception_group_with_db_pool_timeout_returns_service_busy() -> None:
    app = FastAPI()
    app.exception_handler(Exception)(exceptions.unhandled_exception_handler)

    @app.get("/boom")
    async def boom() -> None:
        raise ExceptionGroup(
            "middleware wrapped",
            [SQLAlchemyTimeoutError("pool exhausted")],
        )

    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "2"
    assert response.json()["code"] == "SERVICE_BUSY"
