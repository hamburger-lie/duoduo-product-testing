from __future__ import annotations

import logging
from hashlib import sha256

import httpx
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

logger = logging.getLogger(__name__)

VALID_ROLE_TYPES = {"manufacturer", "channel"}

_WECHAT_JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
_WECHAT_TIMEOUT = httpx.Timeout(connect=10.0, read=10.0, write=10.0, pool=10.0)


class AuthService:
    """Auth use cases supporting both real and mock WeChat login."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def login_with_wechat_code(self, code: str) -> WechatLoginResponse:
        """Login via WeChat code. Uses real API when configured, mock otherwise."""

        normalized_code = code.strip()
        if not normalized_code:
            raise AppException(
                code="WECHAT_CODE_INVALID",
                message="Wechat code is invalid",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        from app.core.config import get_settings

        s = get_settings()
        if s.wechat_app_id and s.wechat_app_secret:
            openid, unionid = await self._real_jscode2session(
                code=normalized_code,
                app_id=s.wechat_app_id,
                app_secret=s.wechat_app_secret,
            )
        else:
            logger.info("wechat_mock_login code=%s", normalized_code[:8])
            openid = self._mock_openid(normalized_code)
            unionid = None

        user = await self.users.get_by_openid(openid)
        is_new_user = user is None

        if user is None:
            user = await self.users.create(
                {
                    "openid": openid,
                    "unionid": unionid,
                    "nickname": "未设置",
                    "role_type": None,
                    "credit_balance": 1000,
                    "status": "active",
                }
            )
            await self.session.commit()
        elif unionid and not user.unionid:
            await self.users.update(user, {"unionid": unionid})
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

    # ------------------------------------------------------------------
    # WeChat API
    # ------------------------------------------------------------------

    async def _real_jscode2session(
        self, *, code: str, app_id: str, app_secret: str,
    ) -> tuple[str, str | None]:
        """Call WeChat jscode2session API to exchange code for openid."""

        params = {
            "appid": app_id,
            "secret": app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(timeout=_WECHAT_TIMEOUT) as client:
                resp = await client.get(_WECHAT_JSCODE2SESSION_URL, params=params)
                data = resp.json()
        except httpx.TimeoutException as exc:
            logger.error("wechat_jscode2session_timeout")
            raise AppException(
                code="WECHAT_SERVICE_TIMEOUT",
                message="WeChat service timeout",
                http_status=status.HTTP_502_BAD_GATEWAY,
            ) from exc
        except httpx.RequestError as exc:
            logger.error("wechat_jscode2session_network_error err=%s", exc)
            raise AppException(
                code="WECHAT_SERVICE_UNAVAILABLE",
                message="WeChat service unavailable",
                http_status=status.HTTP_502_BAD_GATEWAY,
            ) from exc

        errcode = data.get("errcode", 0)
        if errcode != 0:
            errmsg = data.get("errmsg", "unknown")
            logger.warning(
                "wechat_jscode2session_failed errcode=%d errmsg=%s",
                errcode,
                errmsg,
            )
            if errcode == 40029:
                raise AppException(
                    code="WECHAT_CODE_INVALID",
                    message="WeChat code is invalid or expired",
                    http_status=status.HTTP_400_BAD_REQUEST,
                )
            if errcode == 45011:
                raise AppException(
                    code="WECHAT_RATE_LIMITED",
                    message="WeChat API rate limited",
                    http_status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            raise AppException(
                code="WECHAT_LOGIN_FAILED",
                message=f"WeChat login failed: {errmsg}",
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        openid = data.get("openid")
        if not openid:
            logger.error("wechat_jscode2session_no_openid data=%s", data)
            raise AppException(
                code="WECHAT_LOGIN_FAILED",
                message="WeChat login failed: no openid returned",
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        logger.info("wechat_real_login openid=%s...%s", openid[:4], openid[-4:])
        return openid, data.get("unionid")

    # ------------------------------------------------------------------
    # Mock helpers
    # ------------------------------------------------------------------

    def _mock_openid(self, code: str) -> str:
        """Derive a deterministic openid from code for local development."""

        digest = sha256(code.encode("utf-8")).hexdigest()[:16]
        return f"mock_openid_{digest}"

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
