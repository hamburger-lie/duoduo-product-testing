from __future__ import annotations

import pytest

from app.core.config import Settings


def _production_overrides(**kwargs: object) -> dict[str, object]:
    """Return a valid production config dict, with caller overrides applied."""

    base: dict[str, object] = {
        "APP_ENV": "production",
        "APP_SECRET_KEY": "a" * 48,
        "CORS_ALLOWED_ORIGINS": "https://example.com",
        "AI_PROVIDER": "deepseek",
        "DEEPSEEK_API_KEY": "sk-test-key",
        "EVALUATION_RUN_MODE": "celery",
        "WECHAT_APP_ID": "wx_test_id",
        "WECHAT_APP_SECRET": "test_secret",
    }
    base.update(kwargs)
    return base


def test_valid_production_config_passes() -> None:
    """A fully configured production Settings should not raise."""
    Settings(**_production_overrides())  # type: ignore[arg-type]


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        Settings(**_production_overrides(CORS_ALLOWED_ORIGINS="*"))  # type: ignore[arg-type]


def test_production_rejects_mock_ai() -> None:
    with pytest.raises(ValueError, match="AI_PROVIDER"):
        Settings(**_production_overrides(AI_PROVIDER="mock"))  # type: ignore[arg-type]


def test_production_rejects_sync_mode() -> None:
    with pytest.raises(ValueError, match="EVALUATION_RUN_MODE"):
        Settings(**_production_overrides(EVALUATION_RUN_MODE="sync"))  # type: ignore[arg-type]


def test_production_rejects_empty_wechat() -> None:
    with pytest.raises(ValueError, match="WECHAT_APP_ID"):
        Settings(**_production_overrides(WECHAT_APP_ID="", WECHAT_APP_SECRET=""))  # type: ignore[arg-type]


def test_production_rejects_deepseek_without_key() -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        Settings(  # type: ignore[arg-type]
            **_production_overrides(AI_PROVIDER="deepseek", DEEPSEEK_API_KEY="")
        )


def test_production_rejects_short_secret() -> None:
    with pytest.raises(ValueError, match="at least 32 characters"):
        Settings(**_production_overrides(APP_SECRET_KEY="short"))  # type: ignore[arg-type]


def test_production_rejects_default_secret() -> None:
    with pytest.raises(ValueError, match="APP_SECRET_KEY"):
        Settings(  # type: ignore[arg-type]
            **_production_overrides(APP_SECRET_KEY="change_me_for_local_development_only")
        )


def test_development_allows_all_defaults() -> None:
    """Development mode should not reject mock/sync/*."""
    Settings(APP_ENV="development")


def test_db_pool_timeout_can_be_configured() -> None:
    settings = Settings(APP_ENV="development", DB_POOL_TIMEOUT=2.5)  # type: ignore[arg-type]
    assert settings.db_pool_timeout == 2.5


def test_auth_cache_and_activity_settings_can_be_configured() -> None:
    settings = Settings(  # type: ignore[arg-type]
        APP_ENV="development",
        CURRENT_USER_CACHE_TTL_SECONDS=120,
        ACTIVITY_LOG_ENABLED=False,
        ACTIVITY_LOG_SAMPLE_RATE=0.25,
        ACTIVITY_LOG_ASYNC=True,
    )

    assert settings.current_user_cache_ttl_seconds == 120
    assert settings.activity_log_enabled is False
    assert settings.activity_log_sample_rate == 0.25
    assert settings.activity_log_async is True
