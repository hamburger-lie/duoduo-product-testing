from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WechatLoginRequest(BaseModel):
    """Wechat mini-program login request."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=128)
    phone_code: str | None = Field(default=None, max_length=128)
    ref_code: str | None = Field(default=None, max_length=64)


class UserResponse(BaseModel):
    """User response shape defined by the API contract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    nickname: str
    avatar_url: str | None
    role_type: str | None
    credit_balance: int
    phone_number: str | None = None
    phone_masked: str | None = None


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

    role_type: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None


class AvatarUploadResponse(BaseModel):
    """Avatar upload response."""

    model_config = ConfigDict(extra="forbid")

    avatar_url: str


class RefreshTokenResponse(BaseModel):
    """JWT refresh response."""

    model_config = ConfigDict(extra="forbid")

    token: str
    expires_in: int
