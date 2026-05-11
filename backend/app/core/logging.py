from __future__ import annotations

import json
import logging as py_logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings


class JsonFormatter(py_logging.Formatter):
    """Format log records as compact JSON."""

    def format(self, record: py_logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
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

