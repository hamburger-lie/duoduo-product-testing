from __future__ import annotations

import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
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
from app.core.metrics import record_http_request, update_db_pool_metrics
from app.routers.auth import router as auth_router
from app.routers.internal_images import router as internal_images_router
from app.routers.conversation import router as conversation_router
from app.routers.credit import router as credit_router
from app.routers.evaluation import router as evaluation_router
from app.routers.health import router as health_router
from app.routers.history import router as history_router
from app.routers.persona import router as persona_router
from app.routers.product import router as product_router
from app.routers.report import router as report_router
from app.routers.survey import router as survey_router
from app.routers.whitepaper import router as whitepaper_router

configure_logging()
logger = get_logger(__name__)


def _init_sentry() -> None:
    """Initialize Sentry error tracking if DSN is configured."""
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        release=settings.app_version,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            CeleryIntegration(),
            SqlalchemyIntegration(),
        ],
        send_default_pii=False,
    )
    logger.info("sentry_initialized", extra={"environment": settings.app_env})


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _init_sentry()
    from app.core.tracing import init_tracing

    init_tracing()
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

    def _update_pool_metrics() -> None:
        """Sample DB connection pool gauges (best-effort, no-op on failure)."""
        try:
            from app.db.session import _engine

            if _engine is not None:
                pool = _engine.pool
                pool_size = getattr(pool, "size", lambda: 0)()
                pool_checked_out = getattr(pool, "checkedout", lambda: 0)()
                update_db_pool_metrics(pool_size, pool_checked_out)
        except Exception:
            pass

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
        if request.url.path.startswith("/whitepaper-static/"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob: http: https:; "
                "connect-src 'self' http: https:; "
                "worker-src blob:; "
                "frame-ancestors 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        return response

    @app.middleware("http")
    async def metrics_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.monotonic()
        response = await call_next(request)
        if not request.url.path.startswith("/health/"):
            route = request.scope.get("route")
            path_template = getattr(route, "path", request.url.path)
            record_http_request(
                method=request.method,
                path_template=str(path_template),
                status_code=response.status_code,
                duration=time.monotonic() - started_at,
            )
            # Sample DB pool metrics on each non-health request
            _update_pool_metrics()
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
        # Attach trace_id header if tracing is enabled
        from app.core.tracing import get_current_trace_id

        trace_id = get_current_trace_id()
        if trace_id:
            response.headers["X-Trace-Id"] = trace_id
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

    @app.get("/metrics", include_in_schema=False)
    async def get_metrics() -> Response:
        """Return Prometheus metrics in text format."""

        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # Internal local-dev storage endpoint.
    # Only registered when BOTH conditions hold:
    #   STORAGE_ADAPTER=local  AND  APP_ENV != production
    # This prevents the unauthenticated endpoint from being exposed in production.
    _is_local_adapter = settings.storage_adapter.strip().lower() == "local"
    _is_dev = settings.app_env.strip().lower() != "production"
    if _is_local_adapter and _is_dev:
        app.include_router(internal_images_router)

    app.include_router(auth_router)
    app.include_router(product_router)
    app.include_router(persona_router)
    app.include_router(evaluation_router)
    app.include_router(survey_router)
    app.include_router(whitepaper_router)
    app.include_router(report_router)
    app.include_router(conversation_router)
    app.include_router(history_router)
    app.include_router(credit_router)
    app.include_router(health_router)

    static_dir = Path(__file__).parent.parent / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    whitepaper_static_dir = Path(__file__).parent.parent / "whitepaper-static"
    whitepaper_static_dir.mkdir(exist_ok=True)
    app.mount(
        "/whitepaper-static",
        StaticFiles(directory=str(whitepaper_static_dir)),
        name="whitepaper-static",
    )

    return app


app = create_app()
