"""Tests for OpenTelemetry tracing module."""
from __future__ import annotations

from unittest.mock import patch

from app.core.tracing import get_current_trace_id, is_tracing_enabled, optional_span


def test_tracing_disabled_by_default() -> None:
    """Tracing should be disabled when OTEL_ENABLED=false."""
    assert is_tracing_enabled() is False


def test_get_current_trace_id_none_when_disabled() -> None:
    """Should return None when tracing is disabled."""
    assert get_current_trace_id() is None


def test_optional_span_noop_when_disabled() -> None:
    """optional_span should yield None when tracing is disabled."""
    with optional_span("test.operation") as span:
        assert span is None


def test_init_tracing_logs_disabled() -> None:
    """init_tracing should log disabled when OTEL_ENABLED=false."""
    from app.core.tracing import init_tracing

    with patch("app.core.tracing.get_settings") as mock_settings:
        mock_settings.return_value.otel_enabled = False
        init_tracing()

    assert is_tracing_enabled() is False
