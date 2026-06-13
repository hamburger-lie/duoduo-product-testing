from __future__ import annotations

import logging
from datetime import datetime
from hashlib import sha256

import httpx
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException
from app.core.security import create_access_token, invalidate_current_user_cache
from app.core.token_blacklist import blacklist_token
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

# Credit rewards granted at signup / via the share-for-credits program.
NEW_USER_WELCOME_CREDITS = 50
REFERRED_USER_BONUS_CREDITS = 20
REFERRER_BONUS_CREDITS = 20

_WECHAT_JSCODE2SESSION_URL = "https://api.weixin.qq.com/sns/jscode2session"
_WECHAT_ACCESS_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
_WECHAT_PHONE_NUMBER_URL = "https://api.weixin.qq.com/wxa/business/getuserphonenumber"
_WECHAT_TIMEOUT = httpx.Timeout(connect=10.0, read=10.0, write=10.0, pool=10.0)


class AuthService:
    """Auth use cases supporting both real and mock WeChat login."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def login_with_wechat_code(
        self,
        code: str,
        *,
        phone_code: str | None = None,
        ref_code: str | None = None,
    ) -> WechatLoginResponse:
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
            openid = s.wechat_mock_openid.strip() or self._mock_openid(normalized_code)
            unionid = None

        phone_number = await self._resolve_phone_number(
            phone_code=phone_code,
            app_id=s.wechat_app_id,
            app_secret=s.wechat_app_secret,
        )

        user = await self.users.get_by_openid(openid)
        is_new_user = user is None

        if user is None:
            values: dict[str, object] = {
                "openid": openid,
                "unionid": unionid,
                "phone_number": phone_number,
                "nickname": "未设置",
                "role_type": None,
                "credit_balance": NEW_USER_WELCOME_CREDITS,
                "status": "active",
            }
            user = await self.users.create(values)
            from app.services.credit_service import CreditService
            await CreditService(self.session).initialize(user, NEW_USER_WELCOME_CREDITS)
            await self._apply_referral_rewards(new_user=user, ref_code=ref_code)
            await self.session.commit()
        else:
            values = {}
            if unionid and not user.unionid:
                values["unionid"] = unionid
            if phone_number and user.phone_number != phone_number:
                values["phone_number"] = phone_number
            if values:
                user = await self.users.update(user, values)
                await self.session.commit()

        token, expires_in = create_access_token(user_id=user.id)
        return WechatLoginResponse(
            token=token,
            expires_in=expires_in,
            user=self._to_login_user_response(user, is_new_user=is_new_user),
        )

    async def _apply_referral_rewards(
        self,
        *,
        new_user: User,
        ref_code: str | None,
    ) -> None:
        """Grant share-for-credits rewards on a referred user's first signup.

        ``ref_code`` carries the referrer's user id (from the share path
        ``?ref=<user_id>``). Rewards apply only when it resolves to a valid,
        active, different user — so the referred new user gets a bonus and the
        referrer is credited. Rewarding only on first signup prevents existing
        users from farming credits by repeatedly opening share links.
        """

        if not ref_code:
            return
        code = ref_code.strip()
        if not code.isdigit():
            return
        referrer_id = int(code)
        if referrer_id == new_user.id:
            return
        referrer = await self.users.get_by_id(referrer_id)
        if referrer is None or referrer.status != "active":
            return

        from app.services.credit_service import CreditService

        credits = CreditService(self.session)
        await credits.award(
            new_user,
            REFERRED_USER_BONUS_CREDITS,
            reason="referral",
            ref_type="user",
            ref_id=referrer_id,
            note="受邀新用户奖励",
        )
        await credits.award(
            referrer,
            REFERRER_BONUS_CREDITS,
            reason="referral",
            ref_type="user",
            ref_id=new_user.id,
            note="邀请新用户奖励",
        )

    async def update_profile(
        self,
        *,
        user: User,
        role_type: str | None,
        nickname: str | None,
        avatar_url: str | None,
    ) -> UserResponse:
        """Update the authenticated user's profile."""

        values: dict[str, str] = {}
        if role_type is not None:
            if role_type not in VALID_ROLE_TYPES:
                raise AppException(
                    code="INVALID_ROLE_TYPE",
                    message="Role type is invalid",
                    http_status=status.HTTP_400_BAD_REQUEST,
                )
            values["role_type"] = role_type
        if nickname is not None:
            values["nickname"] = nickname
        if avatar_url is not None:
            values["avatar_url"] = avatar_url

        if not values:
            return self._to_user_response(user)

        updated_user = await self.users.update(user, values)
        await self.session.commit()
        await invalidate_current_user_cache(updated_user.id)
        return self._to_user_response(updated_user)

    async def upload_avatar(self, *, user: User, file_bytes: bytes, filename: str) -> str:
        """Save avatar image locally and update user.avatar_url. Returns the public URL."""

        from pathlib import Path
        from uuid import uuid4

        from app.storage.file_validation import MAX_AVATAR_SIZE_BYTES, validate_image_bytes

        avatar_extensions = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
        }
        if len(file_bytes) > MAX_AVATAR_SIZE_BYTES:
            raise AppException(
                code="FILE_TOO_LARGE",
                message="Avatar file is larger than 2MB",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        detected_mime = validate_image_bytes(file_bytes)
        ext = avatar_extensions.get(detected_mime or "")
        if ext is None:
            raise AppException(
                code="INVALID_FILE_TYPE",
                message="Only JPEG, PNG, GIF, or WebP avatar images are allowed",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        _ = filename
        save_dir = Path(__file__).parent.parent.parent / "static" / "avatars"
        save_dir.mkdir(parents=True, exist_ok=True)

        dest = save_dir / f"{user.id}_{uuid4().hex}{ext}"
        dest.write_bytes(file_bytes)

        avatar_url = f"/static/avatars/{dest.name}"
        await self.users.update(user, {"avatar_url": avatar_url})
        await self.session.commit()
        await invalidate_current_user_cache(user.id)
        return avatar_url

    def refresh_token(self, user: User) -> RefreshTokenResponse:
        """Issue a fresh token for the authenticated user."""

        token, expires_in = create_access_token(user_id=user.id)
        return RefreshTokenResponse(token=token, expires_in=expires_in)

    async def logout(self, *, jti: str | None, expires_at: datetime) -> dict[str, str]:
        """Revoke the current access token when it has a JWT ID."""

        if jti:
            await blacklist_token(jti, expires_at)
        return {"message": "ok"}

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

    async def _resolve_phone_number(
        self,
        *,
        phone_code: str | None,
        app_id: str,
        app_secret: str,
    ) -> str | None:
        normalized_phone_code = phone_code.strip() if phone_code else None
        if not normalized_phone_code:
            return None
        if not app_id or not app_secret:
            return "13800138000"

        access_token = await self._get_wechat_access_token(
            app_id=app_id,
            app_secret=app_secret,
        )
        return await self._real_get_phone_number(
            phone_code=normalized_phone_code,
            access_token=access_token,
        )

    async def _get_wechat_access_token(self, *, app_id: str, app_secret: str) -> str:
        params = {
            "grant_type": "client_credential",
            "appid": app_id,
            "secret": app_secret,
        }
        try:
            async with httpx.AsyncClient(timeout=_WECHAT_TIMEOUT) as client:
                resp = await client.get(_WECHAT_ACCESS_TOKEN_URL, params=params)
                data = resp.json()
        except httpx.TimeoutException as exc:
            logger.error("wechat_access_token_timeout")
            raise AppException(
                code="WECHAT_SERVICE_TIMEOUT",
                message="WeChat service timeout",
                http_status=status.HTTP_502_BAD_GATEWAY,
            ) from exc
        except httpx.RequestError as exc:
            logger.error("wechat_access_token_network_error err=%s", exc)
            raise AppException(
                code="WECHAT_SERVICE_UNAVAILABLE",
                message="WeChat service unavailable",
                http_status=status.HTTP_502_BAD_GATEWAY,
            ) from exc

        errcode = data.get("errcode", 0)
        if errcode != 0:
            logger.warning(
                "wechat_access_token_failed errcode=%s errmsg=%s",
                errcode,
                data.get("errmsg"),
            )
            raise AppException(
                code="WECHAT_ACCESS_TOKEN_FAILED",
                message="WeChat access token failed",
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        access_token = data.get("access_token")
        if not access_token:
            raise AppException(
                code="WECHAT_ACCESS_TOKEN_FAILED",
                message="WeChat access token missing",
                http_status=status.HTTP_502_BAD_GATEWAY,
            )
        return str(access_token)

    async def _real_get_phone_number(self, *, phone_code: str, access_token: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=_WECHAT_TIMEOUT) as client:
                resp = await client.post(
                    _WECHAT_PHONE_NUMBER_URL,
                    params={"access_token": access_token},
                    json={"code": phone_code},
                )
                data = resp.json()
        except httpx.TimeoutException as exc:
            logger.error("wechat_phone_timeout")
            raise AppException(
                code="WECHAT_SERVICE_TIMEOUT",
                message="WeChat service timeout",
                http_status=status.HTTP_502_BAD_GATEWAY,
            ) from exc
        except httpx.RequestError as exc:
            logger.error("wechat_phone_network_error err=%s", exc)
            raise AppException(
                code="WECHAT_SERVICE_UNAVAILABLE",
                message="WeChat service unavailable",
                http_status=status.HTTP_502_BAD_GATEWAY,
            ) from exc

        errcode = data.get("errcode", 0)
        if errcode != 0:
            logger.warning(
                "wechat_phone_failed errcode=%s errmsg=%s",
                errcode,
                data.get("errmsg"),
            )
            raise AppException(
                code="WECHAT_PHONE_CODE_INVALID",
                message="WeChat phone code is invalid or expired",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        phone_info = data.get("phone_info") or {}
        phone_number = phone_info.get("purePhoneNumber") or phone_info.get("phoneNumber")
        if not phone_number:
            raise AppException(
                code="WECHAT_PHONE_NOT_RETURNED",
                message="WeChat phone number not returned",
                http_status=status.HTTP_502_BAD_GATEWAY,
            )
        return str(phone_number)

    # ------------------------------------------------------------------
    # Mock helpers
    # ------------------------------------------------------------------

    def _mock_openid(self, code: str) -> str:
        """Derive a deterministic openid from code for local development."""

        digest = sha256(code.encode("utf-8")).hexdigest()[:16]
        return f"mock_openid_{digest}"

    def _mask_phone(self, phone_number: str | None) -> str | None:
        if not phone_number:
            return None
        if len(phone_number) < 7:
            return phone_number
        return f"{phone_number[:3]}****{phone_number[-4:]}"

    def _to_user_response(self, user: User) -> UserResponse:
        return UserResponse(
            id=str(user.id),
            nickname=user.nickname or "未设置",
            avatar_url=user.avatar_url,
            role_type=user.role_type,
            credit_balance=user.credit_balance,
            phone_number=user.phone_number,
            phone_masked=self._mask_phone(user.phone_number),
        )

    def _to_login_user_response(self, user: User, *, is_new_user: bool) -> LoginUserResponse:
        base = self._to_user_response(user)
        return LoginUserResponse(**base.model_dump(), is_new_user=is_new_user)
