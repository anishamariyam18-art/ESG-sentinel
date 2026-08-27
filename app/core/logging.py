"""Structured logging setup.

Logs pipeline progress (document/company/pages/claims/evidence/scores) as
required by the project spec, while guaranteeing secrets never reach a log
record -- even if a caller accidentally includes one in `extra`.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_REDACTED = "***REDACTED***"
_SECRET_KEY_MARKERS = ("key", "secret", "token", "password", "credential", "authorization")


class _DynamicStdoutHandler(logging.StreamHandler):
    """Always writes to the current sys.stdout rather than the object that
    was bound at construction time, so log capture (e.g. pytest's capsys,
    or a reopened stdout) keeps working after setup."""

    @property
    def stream(self):  # type: ignore[override]
        return sys.stdout

    @stream.setter
    def stream(self, value):  # ignore attempts to pin the stream
        pass


def _redact(value: Any, key: str = "") -> Any:
    key_lower = key.lower()
    if any(marker in key_lower for marker in _SECRET_KEY_MARKERS):
        return _REDACTED
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    return value


class SecretRedactionFilter(logging.Filter):
    """Redacts any `extra` field whose key looks like a secret before it
    is emitted, regardless of formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        for attr, value in list(vars(record).items()):
            if attr.startswith("_") or attr in logging.LogRecord.__dict__:
                continue
            setattr(record, attr, _redact(value, attr))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        standard_keys = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__.keys())
        for key, value in vars(record).items():
            if key not in standard_keys and key != "message":
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "INFO") -> None:
    """(Re)configure the root logger with a single JSON stdout handler.
    Safe to call multiple times -- always ends with exactly one handler."""
    root = logging.getLogger()
    root.setLevel(level)

    handler = _DynamicStdoutHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(SecretRedactionFilter())

    root.handlers.clear()
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    if not logging.getLogger().handlers:
        setup_logging()
    return logging.getLogger(name)
