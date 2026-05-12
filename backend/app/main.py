from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
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
from app.routers.evaluation import router as evaluation_router
from app.routers.health import router as health_router
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


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
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
    app.include_router(health_router)
    return app


app = create_app()
