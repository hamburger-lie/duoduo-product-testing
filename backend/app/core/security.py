from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_db_session
from app.core.exceptions import AppException
from app.db.models.user import User
from app.db.repositories.user import UserRepository

security_scheme = HTTPBearer(auto_error=False)
credentials_dependency = Depends(security_scheme)
db_session_dependency = Depends(get_db_session)


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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = credentials_dependency,
    session: AsyncSession = db_session_dependency,
) -> User:
    """Resolve the current authenticated user."""

    if credentials is None:
        raise AppException(
            code="AUTH_REQUIRED",
            message="Authentication is required",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )

    payload = decode_access_token(credentials.credentials)
    raw_user_id = payload.get("user_id")
    if not isinstance(raw_user_id, str) or not raw_user_id.isdigit():
        raise AppException(
            code="AUTH_TOKEN_INVALID",
            message="Token is invalid",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )

    user = await UserRepository(session).get_by_id(int(raw_user_id))
    if user is None:
        raise AppException(
            code="AUTH_TOKEN_INVALID",
            message="Token is invalid",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    return user
