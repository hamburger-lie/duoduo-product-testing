"""OpenTelemetry tracing initialization.

- ``OTEL_ENABLED=false`` (default): tracing fully disabled (NoopTracer).
- ``OTEL_ENABLED=true`` + no endpoint: ConsoleSpanExporter (dev).
- ``OTEL_ENABLED=true`` + endpoint: OTLPSpanExporter (production).

Enabled tracing writes ``trace_id`` into the JSON log payload via the
request logging middleware.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# These are set during init_tracing()
_tracer: Any = None
_TRACING_ENABLED = False


def init_tracing() -> None:
    """Initialize OpenTelemetry if enabled. Safe to call multiple times."""
    global _tracer, _TRACING_ENABLED  # noqa: PLW0603

    settings = get_settings()
    if not settings.otel_enabled:
        logger.info("tracing_disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        resource = Resource.create({"service.name": settings.otel_service_name})
        provider = TracerProvider(resource=resource)

        if settings.otel_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("tracing_otlp endpoint=%s", settings.otel_endpoint)
        else:
            from opentelemetry.sdk.trace.export import (
                ConsoleSpanExporter,
                SimpleSpanProcessor,
            )

            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            logger.info("tracing_console")

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(settings.otel_service_name)
        _TRACING_ENABLED = True

        # Auto-instrument FastAPI if available
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor().instrument()
        except ImportError:
            pass

    except ImportError:
        logger.warning(
            "tracing_init_failed: opentelemetry packages not installed. "
            "Install with: uv add opentelemetry-api opentelemetry-sdk"
        )
    except Exception:
        logger.exception("tracing_init_failed")


def get_tracer() -> Any:
    """Return the global tracer (or None if tracing is disabled)."""
    return _tracer


def is_tracing_enabled() -> bool:
    """Return whether tracing is active."""
    return _TRACING_ENABLED


@contextmanager
def optional_span(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Create a span if tracing is enabled, otherwise no-op context manager.

    Usage::

        with optional_span("ai.complete", provider="deepseek") as span:
            result = await client.complete(...)
            if span:
                span.set_attribute("tokens", result.tokens)
    """
    if _tracer is not None:
        with _tracer.start_as_current_span(name) as span:
            for k, v in attributes.items():
                span.set_attribute(k, v)
            yield span
    else:
        yield None


def get_current_trace_id() -> str | None:
    """Return the current trace ID as hex string, or None."""
    if not _TRACING_ENABLED:
        return None
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return None
