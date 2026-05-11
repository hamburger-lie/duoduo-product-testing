from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.auth import (
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


@router.post("/wechat/login", response_model=WechatLoginResponse)
async def wechat_login(
    payload: WechatLoginRequest,
    session: AsyncSession = db_session_dependency,
) -> WechatLoginResponse:
    """Mock WeChat mini-program login."""

    return await AuthService(session).login_with_wechat_code(payload.code)


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
    )


@router.post("/refresh", response_model=RefreshTokenResponse)
async def refresh_token(
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> RefreshTokenResponse:
    """Refresh the authenticated user's token."""

    return AuthService(session).refresh_token(current_user)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> UserResponse:
    """Return the authenticated user."""

    return AuthService(session).get_me(current_user)
