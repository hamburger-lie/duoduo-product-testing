from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.ai.exceptions import AIContentBlocked
from app.core.config import get_settings
from app.core.exceptions import (
    AppException,
    ai_content_blocked_handler,
    app_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from app.core.logging import configure_logging, get_logger
from app.routers.auth import router as auth_router
from app.routers.conversation import router as conversation_router
from app.routers.credit import router as credit_router
from app.routers.evaluation import router as evaluation_router
from app.routers.health import router as health_router
from app.routers.history import router as history_router
from app.routers.persona import router as persona_router
from app.routers.product import router as product_router
from app.routers.report import router as report_router
from app.routers.survey import router as survey_router

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("application_startup")
    yield
    logger.info("application_shutdown")
    from app.db.session import dispose_engine

    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-Id", "")
        request.state.request_id = request_id or f"req_{uuid4().hex}"
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response

    @app.middleware("http")
    async def security_headers_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        return response

    @app.middleware("http")
    async def request_logging_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.info(
            "http_request",
            extra={
                "event": "http_request",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": round(elapsed_ms, 1),
                "request_id": getattr(request.state, "request_id", ""),
            },
        )
        return response

    @app.exception_handler(AIContentBlocked)
    async def handle_ai_content_blocked(request: Request, exc: AIContentBlocked) -> JSONResponse:
        return await ai_content_blocked_handler(request, exc)

    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        return await app_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        return await unhandled_exception_handler(request, exc)

    app.include_router(auth_router)
    app.include_router(product_router)
    app.include_router(persona_router)
    app.include_router(evaluation_router)
    app.include_router(survey_router)
    app.include_router(report_router)
    app.include_router(conversation_router)
    app.include_router(history_router)
    app.include_router(credit_router)
    app.include_router(health_router)
    return app


app = create_app()
