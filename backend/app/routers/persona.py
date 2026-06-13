from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import RedisCache
from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.persona import (
    PersonaCreateRequest,
    PersonaPageResponse,
    PersonaResponse,
    PersonaUpdateRequest,
)
from app.services.persona_service import PersonaService

router = APIRouter(prefix="/api/v1/personas", tags=["personas"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
persona_list_cache = RedisCache(prefix="personas")
PERSONA_LIST_CACHE_TTL_SECONDS = 300


def _persona_list_cache_key(
    *,
    user_id: int,
    category: str | None,
    page: int,
    page_size: int,
    include_critical: bool,
    owner_scope: str,
    keyword: str | None,
) -> str:
    return (
        f"user:{user_id}:category:{category or ''}:page:{page}:"
        f"page_size:{page_size}:include_critical:{include_critical}:"
        f"owner_scope:{owner_scope}:keyword:{keyword or ''}"
    )


@router.get("", response_model=PersonaPageResponse)
async def list_personas(
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    include_critical: bool = Query(default=True),
    owner_scope: Literal["system", "mine", "all"] = Query(default="all"),
    keyword: str | None = Query(default=None),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> PersonaPageResponse:
    """List personas visible to the current user."""

    cache_key = _persona_list_cache_key(
        user_id=current_user.id,
        category=category,
        page=page,
        page_size=page_size,
        include_critical=include_critical,
        owner_scope=owner_scope,
        keyword=keyword,
    )
    hit, cached = await persona_list_cache.get(cache_key)
    if hit:
        return PersonaPageResponse.model_validate(cached)

    response = await PersonaService(session).list_personas(
        user=current_user,
        category=category,
        page=page,
        page_size=page_size,
        include_critical=include_critical,
        owner_scope=owner_scope,
        keyword=keyword,
    )
    await persona_list_cache.set(
        cache_key,
        response.model_dump(mode="json"),
        ttl=PERSONA_LIST_CACHE_TTL_SECONDS,
    )
    return response


@router.get("/recommend", response_model=PersonaPageResponse)
async def recommend_personas(
    product_id: int,
    count: int = Query(default=20, ge=1, le=100),
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> PersonaPageResponse:
    """Recommend personas for a product."""

    return await PersonaService(session).recommend_personas(
        user=current_user,
        product_id=product_id,
        count=count,
    )


@router.post("", response_model=PersonaResponse)
async def create_persona(
    payload: PersonaCreateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> PersonaResponse:
    """Create a private persona owned by the current user."""

    response = await PersonaService(session).create_persona(
        user=current_user,
        payload=payload,
    )
    await persona_list_cache.delete_pattern(f"user:{current_user.id}:*")
    return response


@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona(
    persona_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> PersonaResponse:
    """Return one full persona visible to the current user."""

    return await PersonaService(session).get_persona(user=current_user, persona_id=persona_id)


@router.patch("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: int,
    payload: PersonaUpdateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> PersonaResponse:
    """Update a private persona owned by the current user."""

    response = await PersonaService(session).update_persona(
        user=current_user,
        persona_id=persona_id,
        payload=payload,
    )
    await persona_list_cache.delete_pattern(f"user:{current_user.id}:*")
    return response


@router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(
    persona_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> Response:
    """Soft-delete a private persona owned by the current user."""

    await PersonaService(session).delete_persona(user=current_user, persona_id=persona_id)
    await persona_list_cache.delete_pattern(f"user:{current_user.id}:*")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
