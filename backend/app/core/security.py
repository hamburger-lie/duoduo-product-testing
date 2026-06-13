from __future__ import annotations

import asyncio
import random
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core import token_blacklist
from app.core.cache import RedisCache
from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.exceptions import AppException
from app.db.models.user import User
from app.db.models.user_activity_event import UserActivityEvent
from app.db.repositories.user import UserRepository

security_scheme = HTTPBearer(auto_error=False)
credentials_dependency = Depends(security_scheme)
db_session_dependency = Depends(get_db_session)
current_user_cache = RedisCache(prefix="current_user")
_SAFE_CACHE_METHODS = {"GET", "HEAD", "OPTIONS"}


def create_access_token(*, user_id: int) -> tuple[str, int]:
    """Create a signed JWT access token."""

    settings = get_settings()
    expires_delta = timedelta(days=settings.app_jwt_expire_days)
    issued_at = datetime.now(UTC)
    expires_at = issued_at + expires_delta
    payload: dict[str, Any] = {
        "user_id": str(user_id),
        "iat": issued_at,
        "exp": expires_at,
        "jti": uuid4().hex,
    }
    token = jwt.encode(payload, settings.app_secret_key, algorithm="HS256")
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
    except ExpiredSignatureError as exc:
        raise AppException(
            code="AUTH_TOKEN_EXPIRED",
            message="Token has expired",
            http_status=status.HTTP_401_UNAUTHORIZED,
        ) from exc
    except InvalidTokenError as exc:
        raise AppException(
            code="AUTH_TOKEN_INVALID",
            message="Token is invalid",
            http_status=status.HTTP_401_UNAUTHORIZED,
        ) from exc
    return dict(payload)


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = credentials_dependency,
) -> str:
    """Extract the bearer token from the Authorization header."""

    if credentials is None:
        raise AppException(
            code="AUTH_REQUIRED",
            message="Authentication is required",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    return credentials.credentials


token_dependency = Depends(get_bearer_token)


async def _record_user_activity(
    *,
    request: Request,
    session: AsyncSession,
    user: User,
) -> None:
    """Best-effort activity audit for authenticated API requests."""

    settings = get_settings()
    if not settings.activity_log_enabled or settings.activity_log_sample_rate <= 0:
        return
    if random.random() >= settings.activity_log_sample_rate:
        return

    bind = session.bind
    if bind is None:
        return

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    event_values = {
        "user_id": user.id,
        "event_type": "api_request",
        "path": request.url.path[:255],
        "method": request.method[:16],
        "request_id": (getattr(request.state, "request_id", "") or "")[:64] or None,
        "ip": client_ip[:64] if client_ip else None,
        "user_agent": user_agent[:512] if user_agent else None,
        "event_metadata": {
            "query": str(request.url.query)[:512],
        },
    }

    if settings.activity_log_async:
        asyncio.create_task(_write_user_activity(bind=bind, event_values=event_values))
        return

    await _write_user_activity(bind=bind, event_values=event_values)


async def _write_user_activity(*, bind: object, event_values: dict[str, object]) -> None:
    """Write one activity event with its own short-lived session."""

    activity_session_factory = async_sessionmaker(
        bind=bind,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    try:
        async with activity_session_factory() as activity_session:
            event = UserActivityEvent(**event_values)
            activity_session.add(event)
            await activity_session.commit()
    except SQLAlchemyError:
        return


def _current_user_cache_enabled(request: Request) -> bool:
    settings = get_settings()
    return (
        settings.current_user_cache_ttl_seconds > 0
        and request.method.upper() in _SAFE_CACHE_METHODS
    )


def _user_cache_key(user_id: int) -> str:
    return f"user:{user_id}"


async def invalidate_current_user_cache(user_id: int) -> None:
    """Drop a cached auth user after profile or balance changes."""

    await current_user_cache.delete(_user_cache_key(user_id))


def _user_to_cache_payload(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "openid": user.openid,
        "unionid": user.unionid,
        "phone_number": user.phone_number,
        "nickname": user.nickname,
        "avatar_url": user.avatar_url,
        "role_type": user.role_type,
        "credit_balance": user.credit_balance,
        "status": user.status,
        "is_plus": user.is_plus,
    }


def _user_from_cache_payload(payload: object) -> User | None:
    if not isinstance(payload, dict):
        return None
    user_id = payload.get("id")
    openid = payload.get("openid")
    if not isinstance(user_id, int) or not isinstance(openid, str):
        return None
    return User(
        id=user_id,
        openid=openid,
        unionid=payload.get("unionid") if isinstance(payload.get("unionid"), str) else None,
        phone_number=(
            payload.get("phone_number")
            if isinstance(payload.get("phone_number"), str)
            else None
        ),
        nickname=payload.get("nickname") if isinstance(payload.get("nickname"), str) else None,
        avatar_url=(
            payload.get("avatar_url") if isinstance(payload.get("avatar_url"), str) else None
        ),
        role_type=(
            payload.get("role_type") if isinstance(payload.get("role_type"), str) else None
        ),
        credit_balance=(
            payload.get("credit_balance")
            if isinstance(payload.get("credit_balance"), int)
            else 0
        ),
        status=payload.get("status") if isinstance(payload.get("status"), str) else "active",
        is_plus=payload.get("is_plus") if isinstance(payload.get("is_plus"), bool) else False,
    )


async def get_current_user(
    request: Request,
    token: str = token_dependency,
    session: AsyncSession = db_session_dependency,
) -> User:
    """Resolve the current authenticated user."""

    payload = decode_access_token(token)
    raw_jti = payload.get("jti")
    if isinstance(raw_jti, str) and await token_blacklist.is_blacklisted(raw_jti):
        raise AppException(
            code="AUTH_TOKEN_INVALID",
            message="Token is invalid",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )

    raw_user_id = payload.get("user_id")
    if not isinstance(raw_user_id, str) or not raw_user_id.isdigit():
        raise AppException(
            code="AUTH_TOKEN_INVALID",
            message="Token is invalid",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )

    user_id = int(raw_user_id)
    if _current_user_cache_enabled(request):
        hit, cached = await current_user_cache.get(_user_cache_key(user_id))
        if hit:
            cached_user = _user_from_cache_payload(cached)
            if cached_user is not None:
                await _record_user_activity(request=request, session=session, user=cached_user)
                return cached_user

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise AppException(
            code="AUTH_TOKEN_INVALID",
            message="Token is invalid",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    if _current_user_cache_enabled(request):
        await current_user_cache.set(
            _user_cache_key(user.id),
            _user_to_cache_payload(user),
            ttl=get_settings().current_user_cache_ttl_seconds,
        )
    await _record_user_activity(request=request, session=session, user=user)
    return user


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = credentials_dependency,
    session: AsyncSession = db_session_dependency,
) -> User | None:
    """Resolve the current user when a bearer token is present."""

    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    raw_jti = payload.get("jti")
    if isinstance(raw_jti, str) and await token_blacklist.is_blacklisted(raw_jti):
        return None

    raw_user_id = payload.get("user_id")
    if not isinstance(raw_user_id, str) or not raw_user_id.isdigit():
        return None
    return await UserRepository(session).get_by_id(int(raw_user_id))
