from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.exceptions import AppException
from app.core.rate_limit import IPRateLimiter
from app.core.security import decode_access_token, get_bearer_token, get_current_user
from app.db.models.user import User
from app.schemas.auth import (
    AvatarUploadResponse,
    ProfileUpdateRequest,
    RefreshTokenResponse,
    UserResponse,
    WechatLoginRequest,
    WechatLoginResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
token_dependency = Depends(get_bearer_token)
login_rate_limit_dependency = Depends(IPRateLimiter(limit=10, window=60))


@router.post("/wechat/login", response_model=WechatLoginResponse)
async def wechat_login(
    payload: WechatLoginRequest,
    _rl: None = login_rate_limit_dependency,
    session: AsyncSession = db_session_dependency,
) -> WechatLoginResponse:
    """Mock WeChat mini-program login."""

    return await AuthService(session).login_with_wechat_code(
        payload.code,
        phone_code=payload.phone_code,
        ref_code=payload.ref_code,
    )


@router.patch("/profile", response_model=UserResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> UserResponse:
    """Update the authenticated user's profile."""

    return await AuthService(session).update_profile(
        user=current_user,
        role_type=payload.role_type,
        nickname=payload.nickname,
        avatar_url=payload.avatar_url,
    )


@router.post("/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> AvatarUploadResponse:
    """Upload and set the authenticated user's avatar image."""

    file_bytes = await file.read()
    avatar_url = await AuthService(session).upload_avatar(
        user=current_user,
        file_bytes=file_bytes,
        filename=file.filename or "avatar.jpg",
    )
    return AvatarUploadResponse(avatar_url=avatar_url)


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> RefreshTokenResponse:
    """Refresh the authenticated user's token."""

    return AuthService(session).refresh_token(current_user)


@router.post("/logout")
async def logout(
    current_user: User = current_user_dependency,
    token: str = token_dependency,
    session: AsyncSession = db_session_dependency,
) -> dict[str, str]:
    """Logout the current user by revoking the active bearer token."""

    _ = current_user
    payload = decode_access_token(token)
    raw_jti = payload.get("jti")
    raw_exp = payload.get("exp")
    if not isinstance(raw_exp, int):
        raise AppException(
            code="AUTH_TOKEN_INVALID",
            message="Token is invalid",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    expires_at = datetime.fromtimestamp(raw_exp, tz=UTC)
    return await AuthService(session).logout(
        jti=raw_jti if isinstance(raw_jti, str) else None,
        expires_at=expires_at,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> UserResponse:
    """Return the authenticated user."""

    return AuthService(session).get_me(current_user)
