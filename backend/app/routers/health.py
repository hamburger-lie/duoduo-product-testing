from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.schemas.health import HealthResponse, LiveHealthResponse, ReadyHealthResponse
from app.services.health_service import HealthService

router = APIRouter(tags=["health"])
db_session_dependency = Depends(get_db_session)


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Return application health status."""

    return HealthService().get_health()


@router.get("/health/live", response_model=LiveHealthResponse)
async def get_health_live() -> LiveHealthResponse:
    """Return liveness probe status."""

    return HealthService().get_live()


@router.get("/health/ready", response_model=ReadyHealthResponse)
async def get_health_ready(
    session: AsyncSession = db_session_dependency,
) -> ReadyHealthResponse:
    """Return readiness probe status."""

    return await HealthService().get_ready(session)
