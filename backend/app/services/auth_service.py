from __future__ import annotations

from hashlib import sha256

from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import create_access_token
from app.db.models.user import User
from app.db.repositories.user import UserRepository
from app.schemas.auth import (
    LoginUserResponse,
    RefreshTokenResponse,
    UserResponse,
    WechatLoginResponse,
)

VALID_ROLE_TYPES = {"manufacturer", "channel"}


class AuthService:
    """Auth use cases for the mock WeChat login flow."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def login_with_wechat_code(self, code: str) -> WechatLoginResponse:
        """Mock WeChat login by deriving a deterministic openid from code."""

        normalized_code = code.strip()
        if not normalized_code:
            raise AppException(
                code="WECHAT_CODE_INVALID",
                message="Wechat code is invalid",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        openid = self._mock_openid(normalized_code)
        user = await self.users.get_by_openid(openid)
        is_new_user = user is None

        if user is None:
            user = await self.users.create(
                {
                    "openid": openid,
                    "nickname": "未设置",
                    "role_type": None,
                    "credit_balance": 1000,
                    "status": "active",
                }
            )
            await self.session.commit()

        token, expires_in = create_access_token(user_id=user.id)
        return WechatLoginResponse(
            token=token,
            expires_in=expires_in,
            user=self._to_login_user_response(user, is_new_user=is_new_user),
        )

    async def update_profile(
        self,
        *,
        user: User,
        role_type: str,
        nickname: str | None,
    ) -> UserResponse:
        """Update the authenticated user's profile."""

        if role_type not in VALID_ROLE_TYPES:
            raise AppException(
                code="INVALID_ROLE_TYPE",
                message="Role type is invalid",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        values: dict[str, str] = {"role_type": role_type}
        if nickname is not None:
            values["nickname"] = nickname

        updated_user = await self.users.update(user, values)
        await self.session.commit()
        return self._to_user_response(updated_user)

    def refresh_token(self, user: User) -> RefreshTokenResponse:
        """Issue a fresh token for the authenticated user."""

        token, expires_in = create_access_token(user_id=user.id)
        return RefreshTokenResponse(token=token, expires_in=expires_in)

    def get_me(self, user: User) -> UserResponse:
        """Return the authenticated user."""

        return self._to_user_response(user)

    def _to_user_response(self, user: User) -> UserResponse:
        return UserResponse(
            id=str(user.id),
            nickname=user.nickname or "未设置",
            avatar_url=user.avatar_url,
            role_type=user.role_type,
            credit_balance=user.credit_balance,
        )

    def _to_login_user_response(self, user: User, *, is_new_user: bool) -> LoginUserResponse:
        base = self._to_user_response(user)
        return LoginUserResponse(**base.model_dump(), is_new_user=is_new_user)

    def _mock_openid(self, code: str) -> str:
        digest = sha256(code.encode("utf-8")).hexdigest()[:16]
        return f"mock_openid_{digest}"

