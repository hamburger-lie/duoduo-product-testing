from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.schemas.common import ErrorResponse


class AppException(Exception):
    """Application exception with API contract error payload."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        http_status: int,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details


def _contains_db_pool_timeout(exc: BaseException) -> bool:
    if isinstance(exc, SQLAlchemyTimeoutError):
        return True
    nested = getattr(exc, "exceptions", None)
    if not nested:
        return False
    return any(_contains_db_pool_timeout(item) for item in nested)


def _build_error_response(
    *,
    request: Request,
    code: str,
    message: str,
    http_status: int,
    details: Any = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "") or f"req_{uuid4().hex}"
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    payload = ErrorResponse(
        code=code,
        message=message,
        details=details,
        request_id=request_id,
        timestamp=timestamp,
    )
    return JSONResponse(
        status_code=http_status,
        content=jsonable_encoder(payload.model_dump()),
        headers={"X-Request-Id": request_id},
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Render an AppException using the contract error format."""

    return _build_error_response(
        request=request,
        code=exc.code,
        message=exc.message,
        http_status=exc.http_status,
        details=exc.details,
    )


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Render request validation failures using the contract error format."""

    return _build_error_response(
        request=request,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        http_status=status.HTTP_400_BAD_REQUEST,
        details=exc.errors(),
    )


async def ai_content_blocked_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render AIContentBlocked as a 451 response."""

    return _build_error_response(
        request=request,
        code="AI_CONTENT_BLOCKED",
        message="Content blocked by moderation",
        http_status=451,
    )


async def db_pool_timeout_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Render DB connection pool saturation as a retryable busy response."""

    _ = exc
    response = _build_error_response(
        request=request,
        code="SERVICE_BUSY",
        message="系统繁忙，请稍后再试",
        http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
    )
    response.headers["Retry-After"] = "2"
    return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render unexpected exceptions using the contract error format.

    In non-production environments the exception class name is included in
    ``details`` to ease debugging.  In production it is omitted so internal
    implementation details are never leaked to clients.
    """

    from app.core.config import get_settings

    if _contains_db_pool_timeout(exc):
        return await db_pool_timeout_exception_handler(request, exc)

    details: dict[str, str] | None = None
    if get_settings().app_env != "production":
        details = {"error": exc.__class__.__name__}

    return _build_error_response(
        request=request,
        code="INTERNAL_ERROR",
        message="Internal server error",
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details=details,
    )
