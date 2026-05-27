from __future__ import annotations

import httpx
import redis.asyncio as aioredis
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
        """Return readiness status with a real database check.

        Checks (in order):
        1. PostgreSQL — SELECT 1
        2. Redis — PING
        3. Qdrant — GET /healthz (HTTP)

        Any failure returns 503 with the failed component listed.
        """
        settings = get_settings()
        checks: dict[str, str] = {}
        failed = False

        # ---- 1. Database ----
        try:
            await session.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "failed"
            failed = True

        # ---- 2. Redis ----
        try:
            client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
            ping_result = client.ping()
            if hasattr(ping_result, "__await__"):
                await ping_result
            await client.aclose()
            checks["redis"] = "ok"
        except Exception:
            checks["redis"] = "failed"
            failed = True

        # ---- 3. Qdrant ----
        qdrant_url = getattr(settings, "qdrant_url", "http://localhost:6333")
        try:
            async with httpx.AsyncClient(timeout=2.0) as http:
                resp = await http.get(f"{qdrant_url}/healthz")
            checks["qdrant"] = "ok" if resp.status_code == 200 else "failed"
            if resp.status_code != 200:
                failed = True
        except Exception:
            checks["qdrant"] = "failed"
            failed = True

        if failed:
            raise AppException(
                code="SERVICE_UNAVAILABLE",
                message="One or more dependencies are unavailable",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                details=checks,
            )

        return ReadyHealthResponse(
            status="ok",
            checks=checks,
        )
