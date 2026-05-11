from __future__ import annotations

from fastapi import status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AppException
from app.schemas.health import HealthResponse, LiveHealthResponse, ReadyHealthResponse


class HealthService:
    """Service layer for health checks."""

    def get_health(self) -> HealthResponse:
        """Return the static health response for the API skeleton."""

        settings = get_settings()
        return HealthResponse(
            status="ok",
            service=settings.app_name,
            version=settings.app_version,
        )

    def get_live(self) -> LiveHealthResponse:
        """Return liveness status."""

        return LiveHealthResponse(status="ok")

    async def get_ready(self, session: AsyncSession) -> ReadyHealthResponse:
        """Return readiness status with a real database check."""

        try:
            await session.execute(text("SELECT 1"))
        except Exception as exc:
            raise AppException(
                code="SERVICE_UNAVAILABLE",
                message="Database is unavailable",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                details={"database": "failed"},
            ) from exc

        return ReadyHealthResponse(
            status="ok",
            checks={
                "database": "ok",
                "redis": "skipped",
                "qdrant": "skipped",
                "ark": "skipped",
            },
        )
