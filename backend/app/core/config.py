from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, model_validator
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
    cors_allowed_origins: str = Field(default="*", alias="CORS_ALLOWED_ORIGINS")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/duoduo",
        alias="DATABASE_URL",
    )
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=1800, alias="DB_POOL_RECYCLE")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    evaluation_run_mode: str = Field(default="sync", alias="EVALUATION_RUN_MODE")
    followup_webhook_url: str = Field(default="", alias="FOLLOWUP_WEBHOOK_URL")
    followup_webhook_secret: str = Field(default="", alias="FOLLOWUP_WEBHOOK_SECRET")
    followup_webhook_timeout_seconds: float = Field(
        default=5.0,
        alias="FOLLOWUP_WEBHOOK_TIMEOUT_SECONDS",
    )

    # WeChat mini-program settings (leave empty to use mock login)
    wechat_app_id: str = Field(default="", alias="WECHAT_APP_ID")
    wechat_app_secret: str = Field(default="", alias="WECHAT_APP_SECRET")

    # Credit cost per persona in an evaluation run
    credit_cost_per_persona: int = Field(default=10, alias="CREDIT_COST_PER_PERSONA")

    # AI cost estimate settings. Defaults are zero until finance confirms pricing.
    ai_input_price_yuan_per_1k: Decimal = Field(
        default=Decimal("0.0000"),
        alias="AI_INPUT_PRICE_YUAN_PER_1K",
    )
    ai_output_price_yuan_per_1k: Decimal = Field(
        default=Decimal("0.0000"),
        alias="AI_OUTPUT_PRICE_YUAN_PER_1K",
    )
    recharge_callback_secret: str = Field(default="", alias="RECHARGE_CALLBACK_SECRET")

    # Sentry error tracking (leave empty to disable)
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(
        default=0.1, alias="SENTRY_TRACES_SAMPLE_RATE"
    )

    # OpenTelemetry tracing (leave disabled by default)
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    otel_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_service_name: str = Field(default="duoduo-api", alias="OTEL_SERVICE_NAME")

    # AI provider: "mock" | "deepseek" | "ark" (deprecated)
    ai_provider: str = Field(default="mock", alias="AI_PROVIDER")

    # DeepSeek AI settings (文本主力)
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        alias="DEEPSEEK_BASE_URL",
    )
    deepseek_model: str = Field(default="deepseek-v4-flash", alias="DEEPSEEK_MODEL")
    deepseek_model_pro: str = Field(
        default="deepseek-v4-flash",
        alias="DEEPSEEK_MODEL_PRO",
    )
    deepseek_model_flash: str = Field(
        default="deepseek-v4-flash",
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

    @model_validator(mode="after")
    def validate_production_secrets(self) -> Settings:
        """Validate production-only secret and configuration requirements.

        Prevents production from starting with insecure defaults such as
        mock AI, wildcard CORS, sync evaluation mode, or missing WeChat
        credentials.
        """

        if self.app_env != "production":
            return self

        # --- Secret key ---
        if self.app_secret_key == "change_me_for_local_development_only":
            raise ValueError(
                "APP_SECRET_KEY must be changed from default in production. "
                'Generate one with: python -c "import secrets; '
                'print(secrets.token_urlsafe(32))"'
            )
        if len(self.app_secret_key) < 32:
            raise ValueError(
                "APP_SECRET_KEY must be at least 32 characters in production"
            )

        # --- CORS ---
        if self.cors_allowed_origins.strip() == "*":
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must not be '*' in production. "
                "Set to comma-separated allowed origins, e.g. "
                "'https://your-domain.com'"
            )

        # --- AI provider ---
        if self.ai_provider == "mock":
            raise ValueError(
                "AI_PROVIDER must not be 'mock' in production. "
                "Set to 'deepseek' or another real provider."
            )
        if self.ai_provider == "deepseek" and not self.deepseek_api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is required when AI_PROVIDER='deepseek'"
            )

        # --- Evaluation run mode ---
        if self.evaluation_run_mode.strip().lower() == "sync":
            raise ValueError(
                "EVALUATION_RUN_MODE must not be 'sync' in production. "
                "Set to 'celery' for async task execution."
            )

        if self.followup_webhook_url and len(self.followup_webhook_secret) < 32:
            raise ValueError(
                "FOLLOWUP_WEBHOOK_SECRET must be at least 32 characters when "
                "FOLLOWUP_WEBHOOK_URL is set in production"
            )

        # --- WeChat credentials ---
        if not self.wechat_app_id or not self.wechat_app_secret:
            raise ValueError(
                "WECHAT_APP_ID and WECHAT_APP_SECRET are required in production. "
                "Without them, mock login is enabled, allowing unauthenticated access."
            )

        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""

    return Settings()
