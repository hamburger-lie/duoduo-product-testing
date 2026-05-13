from __future__ import annotations

import json
import logging as py_logging
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

# Patterns that must never appear verbatim in log output.
# Each tuple is (pattern, replacement).
_SENSITIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # JWT Bearer tokens  (eyJ…)
    (re.compile(r"eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"), "***JWT***"),
    # Generic API keys / secret-like strings (≥32 hex chars)
    (re.compile(r"[A-Za-z0-9]{32,}"), lambda m: m.group()[:4] + "***"),  # type: ignore[arg-type]
    # Authorization header values
    (re.compile(r"(Bearer\s+)\S+", re.IGNORECASE), r"\1***"),
    # Signed upload URLs (TOS / S3)
    (re.compile(r"https?://[^\s]+X-Amz-Signature=[^\s&]+[^\s]*"), "***SIGNED_URL***"),
    (re.compile(r"https?://[^\s]+Signature=[^\s&]+[^\s]*"), "***SIGNED_URL***"),
]


def _scrub(text: str) -> str:
    """Replace sensitive patterns in ``text`` with placeholders."""
    for pattern, replacement in _SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)  # type: ignore[call-overload]
    return text


class JsonFormatter(py_logging.Formatter):
    """Format log records as compact JSON, scrubbing sensitive values."""

    def format(self, record: py_logging.LogRecord) -> str:
        raw_message = _scrub(record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": raw_message,
        }
        if hasattr(record, "request_id"):
            payload["request_id"] = record.request_id
        if hasattr(record, "user_id"):
            payload["user_id"] = record.user_id
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Configure application logging once at startup."""

    settings = get_settings()
    root_logger = py_logging.getLogger()
    root_logger.setLevel(settings.log_level.upper())
    root_logger.handlers.clear()

    handler = py_logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root_logger.addHandler(handler)


def get_logger(name: str) -> py_logging.Logger:
    """Return a configured logger."""

    return py_logging.getLogger(name)

