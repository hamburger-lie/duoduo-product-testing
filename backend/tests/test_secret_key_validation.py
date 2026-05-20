from __future__ import annotations

import pytest

from app.core.config import Settings

DEFAULT_SECRET_KEY = "change_me_for_local_development_only"
VALID_SECRET_KEY = "x" * 32


def test_production_default_key_raises() -> None:
    with pytest.raises(ValueError, match="APP_SECRET_KEY must be changed"):
        Settings(APP_ENV="production", APP_SECRET_KEY=DEFAULT_SECRET_KEY)


def test_production_short_key_raises() -> None:
    with pytest.raises(ValueError, match="APP_SECRET_KEY must be at least 32"):
        Settings(APP_ENV="production", APP_SECRET_KEY="short")


def test_production_valid_key_ok() -> None:
    settings = Settings(
        APP_ENV="production",
        APP_SECRET_KEY=VALID_SECRET_KEY,
        CORS_ALLOWED_ORIGINS="https://example.com",
        AI_PROVIDER="deepseek",
        DEEPSEEK_API_KEY="sk-test-key",
        EVALUATION_RUN_MODE="celery",
        WECHAT_APP_ID="wx1234567890",
        WECHAT_APP_SECRET="test_secret_value",
    )

    assert settings.app_env == "production"
    assert settings.app_secret_key == VALID_SECRET_KEY


def test_development_default_key_ok() -> None:
    settings = Settings(APP_ENV="development", APP_SECRET_KEY=DEFAULT_SECRET_KEY)

    assert settings.app_env == "development"
    assert settings.app_secret_key == DEFAULT_SECRET_KEY
