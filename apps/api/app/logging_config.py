"""Structured JSON logging for the API.

Emits one JSON object per log line so that log aggregators can parse and filter.
Falls back to human-readable output when LOG_FORMAT=text.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + ".%03dZ" % int(record.msecs),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("request_id", "tenant_id", "conversation_id", "call_id",
                    "user_id", "path", "method", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record):
        base = "%s [%s] %s: %s" % (
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
            record.levelname,
            record.name,
            record.getMessage(),
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = os.getenv("LOG_FORMAT", "json").lower()

    formatter = JsonFormatter() if fmt == "json" else TextFormatter()

    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root.addHandler(handler)

    logging.getLogger("uvicorn.access").setLevel("WARNING")
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("sqlalchemy.engine").setLevel("WARNING")
    logging.getLogger("websockets").setLevel("WARNING")


def new_request_id():
    return uuid.uuid4().hex[:16]


def log_extra(**kwargs):
    return {k: v for k, v in kwargs.items() if v is not None}
