from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class WechatLoginRequest(BaseModel):
    """Wechat mini-program login request."""

    model_config = ConfigDict(extra="forbid")

    code: str


class UserResponse(BaseModel):
    """User response shape defined by the API contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    nickname: str
    avatar_url: str | None
    role_type: str | None
    credit_balance: int


class LoginUserResponse(UserResponse):
    """User response shape for login."""

    is_new_user: bool


class WechatLoginResponse(BaseModel):
    """Wechat login response."""

    model_config = ConfigDict(extra="forbid")

    token: str
    expires_in: int
    user: LoginUserResponse


class ProfileUpdateRequest(BaseModel):
    """Profile update request."""

    model_config = ConfigDict(extra="forbid")

    role_type: str
    nickname: str | None = None


class RefreshTokenResponse(BaseModel):
    """JWT refresh response."""

    model_config = ConfigDict(extra="forbid")

    token: str
    expires_in: int

