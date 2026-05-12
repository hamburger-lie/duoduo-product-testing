from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="duoduo-product-testing-api", alias="APP_NAME")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_secret_key: str = Field(
        default="change_me_for_local_development_only",
        alias="APP_SECRET_KEY",
    )
    app_jwt_expire_days: int = Field(default=7, alias="APP_JWT_EXPIRE_DAYS")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/duoduo",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # WeChat mini-program settings (leave empty to use mock login)
    wechat_app_id: str = Field(default="", alias="WECHAT_APP_ID")
    wechat_app_secret: str = Field(default="", alias="WECHAT_APP_SECRET")

    # AI provider: "mock" | "deepseek" | "ark" (deprecated)
    ai_provider: str = Field(default="mock", alias="AI_PROVIDER")

    # DeepSeek AI settings (文本主力)
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        alias="DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(default="deepseek-chat", alias="DEEPSEEK_MODEL")
    deepseek_model_pro: str = Field(
        default="deepseek-chat",
        alias="DEEPSEEK_MODEL_PRO",
    )
    deepseek_model_flash: str = Field(
        default="deepseek-chat",
        alias="DEEPSEEK_MODEL_FLASH",
    )

    # 智谱 GLM (多模态/视觉，产品图片理解专用)
    zhipu_api_key: str = Field(default="", alias="ZHIPU_API_KEY")
    zhipu_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        alias="ZHIPU_BASE_URL",
    )
    zhipu_model_vision: str = Field(default="glm-4.6v", alias="ZHIPU_MODEL_VISION")

    # DEPRECATED: 火山方舟 (Ark/Doubao) — 保留向后兼容
    ark_api_key: str = Field(default="", alias="ARK_API_KEY")
    ark_base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3",
        alias="ARK_BASE_URL",
    )
    ark_ep_doubao_seed_16: str = Field(default="", alias="ARK_EP_DOUBAO_SEED_16")
    ark_ep_doubao_15_pro_character: str = Field(
        default="", alias="ARK_EP_DOUBAO_15_PRO_CHARACTER"
    )
    ark_ep_doubao_15_lite: str = Field(default="", alias="ARK_EP_DOUBAO_15_LITE")
    ark_ep_vision_pro: str = Field(default="", alias="ARK_EP_VISION_PRO")
    ark_ep_embedding: str = Field(default="", alias="ARK_EP_EMBEDDING")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
