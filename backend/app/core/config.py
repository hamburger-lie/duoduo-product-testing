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
    db_pool_timeout: float = Field(default=30.0, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=1800, alias="DB_POOL_RECYCLE")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    current_user_cache_ttl_seconds: int = Field(
        default=300,
        ge=0,
        alias="CURRENT_USER_CACHE_TTL_SECONDS",
    )
    activity_log_enabled: bool = Field(default=True, alias="ACTIVITY_LOG_ENABLED")
    activity_log_sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        alias="ACTIVITY_LOG_SAMPLE_RATE",
    )
    activity_log_async: bool = Field(default=False, alias="ACTIVITY_LOG_ASYNC")
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    evaluation_run_mode: str = Field(default="sync", alias="EVALUATION_RUN_MODE")
    max_running_evaluations_per_user: int = Field(
        default=1,
        ge=1,
        alias="MAX_RUNNING_EVALUATIONS_PER_USER",
    )
    persona_answer_concurrency: int = Field(
        default=5,
        ge=1,
        le=5,
        alias="PERSONA_ANSWER_CONCURRENCY",
    )
    followup_webhook_url: str = Field(default="", alias="FOLLOWUP_WEBHOOK_URL")
    followup_webhook_secret: str = Field(default="", alias="FOLLOWUP_WEBHOOK_SECRET")
    followup_webhook_timeout_seconds: float = Field(
        default=5.0,
        alias="FOLLOWUP_WEBHOOK_TIMEOUT_SECONDS",
    )
    survey_ai_timeout_seconds: float = Field(default=8.0, alias="SURVEY_AI_TIMEOUT_SECONDS")
    # Disable DeepSeek reasoning for survey generation. The survey prompt
    # already encodes the full design methodology, so reasoning tokens are
    # mostly wasted latency (~3x slower). Set false in .env to roll back.
    survey_disable_thinking: bool = Field(default=True, alias="SURVEY_DISABLE_THINKING")

    # WeChat mini-program settings (leave empty to use mock login)
    wechat_app_id: str = Field(default="", alias="WECHAT_APP_ID")
    wechat_app_secret: str = Field(default="", alias="WECHAT_APP_SECRET")
    # Optional fixed openid for local/mock login; empty falls back to a
    # deterministic hash of the login code (see AuthService._mock_openid).
    wechat_mock_openid: str = Field(default="", alias="WECHAT_MOCK_OPENID")

    # Credit cost per persona in an evaluation run
    # Flat credit cost per evaluation run (charged once regardless of persona count).
    credit_cost_per_evaluation: int = Field(default=10, alias="CREDIT_COST_PER_EVALUATION")
    # Per-persona cost is disabled; kept at 0 so existing refund paths are no-ops.
    credit_cost_per_persona: int = Field(default=0, alias="CREDIT_COST_PER_PERSONA")

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
    plus_payment_enabled: bool = Field(default=False, alias="PLUS_PAYMENT_ENABLED")

    # WeChat Pay v3 merchant credentials
    wechat_mch_id: str = Field(default="", alias="WECHAT_MCH_ID")
    wechat_pay_key: str = Field(
        default="", alias="WECHAT_PAY_KEY"
    )  # 32-char API v3 key
    wechat_pay_serial_no: str = Field(
        default="", alias="WECHAT_PAY_SERIAL_NO"
    )  # merchant cert serial
    wechat_pay_private_key: str = Field(
        default="", alias="WECHAT_PAY_PRIVATE_KEY"
    )  # PEM, newlines as \n

    # Sentry error tracking (leave empty to disable)
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(
        default=0.1, alias="SENTRY_TRACES_SAMPLE_RATE"
    )

    # OpenTelemetry tracing (leave disabled by default)
    otel_enabled: bool = Field(default=False, alias="OTEL_ENABLED")
    otel_endpoint: str = Field(default="", alias="OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_service_name: str = Field(default="duoduo-api", alias="OTEL_SERVICE_NAME")

    # Whitepaper proxy service (独立白皮书生成服务)
    whitepaper_service_url: str = Field(
        default="http://localhost:18001",
        alias="WHITEPAPER_SERVICE_URL",
    )
    whitepaper_timeout_seconds: float = Field(
        default=300.0,
        alias="WHITEPAPER_TIMEOUT_SECONDS",
    )

    # Storage adapter for product image uploads: "mock" | "local" | "tos"
    # "mock"  — fake TOS URLs, suitable for pure-backend tests (no real images).
    # "local" — stores files on the backend host; local dev only, NOT for production.
    # "tos"   — Volcengine TOS (Tencent-compatible); requires TOS_* vars below.
    storage_adapter: str = Field(default="mock", alias="STORAGE_ADAPTER")

    # Base URL of this backend server (used by LocalProductStorageAdapter to
    # build upload_url / image_url that point back to itself).
    backend_base_url: str = Field(
        default="http://127.0.0.1:8000",
        alias="BACKEND_BASE_URL",
    )

    # === TOS (Volcengine Object Storage) ===
    # Required when STORAGE_ADAPTER=tos
    tos_access_key: str = Field(default="", alias="TOS_ACCESS_KEY")
    tos_secret_key: str = Field(default="", alias="TOS_SECRET_KEY")
    tos_endpoint: str = Field(default="", alias="TOS_ENDPOINT")     # e.g. tos-cn-beijing.volces.com
    tos_region: str = Field(default="", alias="TOS_REGION")         # e.g. cn-beijing
    tos_bucket: str = Field(default="", alias="TOS_BUCKET")         # bucket name
    tos_cdn_domain: str = Field(default="", alias="TOS_CDN_DOMAIN") # e.g. cdn.example.com
    tos_presign_expire_seconds: int = Field(default=3600, alias="TOS_PRESIGN_EXPIRE_SECONDS")

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

    # Vision provider for image extraction: "mock" | "zhipu"
    # Defaults to AI_PROVIDER when not set (so AI_PROVIDER=mock → vision=mock too).
    vision_provider: str = Field(default="", alias="VISION_PROVIDER")

    # Image extraction mode: "vision" | "vision_text"
    # "vision"      — GLM-4V does full field extraction in one call (slower, ~30s)
    # "vision_text" — GLM-4V only extracts raw text, then DeepSeek structures
    #                 fields from that text (faster: ~10s vision + ~3s text)
    image_extract_mode: str = Field(default="vision", alias="IMAGE_EXTRACT_MODE")

    # Vision image pre-processing before sending to GLM-4V
    vision_image_max_side: int = Field(default=720, alias="VISION_IMAGE_MAX_SIDE")
    vision_image_jpeg_quality: int = Field(default=70, alias="VISION_IMAGE_JPEG_QUALITY")

    # Timeout for the full extract-from-images operation (seconds)
    image_extract_timeout_seconds: float = Field(
        default=120.0, alias="IMAGE_EXTRACT_TIMEOUT_SECONDS"
    )

    # In-memory extract result cache TTL (seconds); 0 to disable
    image_extract_cache_ttl_seconds: int = Field(
        default=86400, alias="IMAGE_EXTRACT_CACHE_TTL_SECONDS"
    )

    # Enable verbose AI extract debug logging (raw_text, fields, signed URLs)
    debug_ai_extract: bool = Field(default=False, alias="DEBUG_AI_EXTRACT")

    # 智谱 GLM (多模态/视觉，产品图片理解专用)
    zhipu_api_key: str = Field(default="", alias="ZHIPU_API_KEY")
    zhipu_base_url: str = Field(
        default="https://open.bigmodel.cn/api/paas/v4",
        alias="ZHIPU_BASE_URL",
    )
    zhipu_model_vision: str = Field(default="glm-4.6v", alias="ZHIPU_MODEL_VISION")
    # glm-4.6v 默认"模型自动判断是否思考"，图片字段提取是 OCR 型任务无需推理，
    # 关闭可砍掉隐藏思考 token（中位 ~28s 调用的主要耗时）。.env 设 false 可回滚。
    vision_disable_thinking: bool = Field(default=True, alias="VISION_DISABLE_THINKING")
    # 关思考后正文 = raw_text(~600字) + 9 字段 + 描述，2048 留足余量防截断，
    # 同时为病态长输出兜底。仅在关思考时生效（开思考回滚不加 cap）。
    vision_max_tokens: int = Field(default=2048, alias="VISION_MAX_TOKENS")
    # 并发防护（2核2G + 美博会现场多人同传图）：
    # - 同时在飞的视觉请求上限。豆包并发额度很高（可达数千），不是瓶颈，所以这个
    #   值由服务器内存决定而非提供商。await 阶段每请求仅约 0.5MB，压缩另有线程池
    #   单独限流（OOM 防护在那里），故 48 对 2核2G 仍安全；上线后实测内存可再上调
    #   到 64+。现场纯靠 env 调，不改代码。
    vision_max_concurrency: int = Field(default=48, alias="VISION_MAX_CONCURRENCY")
    # - 同时进行的图片压缩上限。PIL 解压 12MP 图 ≈ 36MB/张，必须卡死避免 OOM。
    vision_compress_workers: int = Field(default=3, alias="VISION_COMPRESS_WORKERS")
    # - 信号量满后还能排队的请求数；超出直接返回"繁忙"，避免无限堆积拖垮进程。
    #   32 并发 + 96 排队 = 容纳 128 在途，100 人现场不触发拒绝，队尾约 50s 内消化。
    vision_max_queue: int = Field(default=96, alias="VISION_MAX_QUEUE")
    # - 失败保底：解析失败/空白卷/超时 时的重试次数（豆包 ~13s/次，重试成本低）。
    vision_max_retries: int = Field(default=2, alias="VISION_MAX_RETRIES")

    # DEPRECATED: 火山方舟 (Ark/Doubao) — 保留向后兼容
    ark_api_key: str = Field(default="", alias="ARK_API_KEY")
    ark_base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3",
        alias="ARK_BASE_URL",
    )
    # 豆包视觉模型（VISION_PROVIDER=doubao 时使用）。mini 实测：质量够、~7s 最快、
    # 并发干净到 20+、最便宜。OpenAI 兼容，复用 vision_disable_thinking / vision_max_tokens。
    ark_model_vision: str = Field(
        default="doubao-seed-2-0-mini-260428", alias="ARK_MODEL_VISION"
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
        """Validate production-only secret and configuration requirements."""

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
