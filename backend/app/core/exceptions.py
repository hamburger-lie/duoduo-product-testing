from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render unexpected exceptions using the contract error format."""

    return _build_error_response(
        request=request,
        code="INTERNAL_ERROR",
        message="Internal server error",
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={"error": exc.__class__.__name__},
    )
