import pathlib

BASE = pathlib.Path(__file__).parent

FILES = {}

FILES["config_validator.py"] = '''"""Startup config validation.

Fails fast when required environment variables are missing or malformed, so the
app refuses to boot in a misconfigured state instead of failing later on the
first request. Called from main.py at import time.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


_REQUIRED_ALWAYS = (
    "DATABASE_URL",
    "JWT_SECRET",
)

_REQUIRED_IN_PRODUCTION = (
    "REDIS_URL",
)

_PATTERN_VALIDATORS = {
    "DATABASE_URL": (
        re.compile(r"^(postgres|postgresql|sqlite)"),
        "must start with postgresql://, postgres://, or sqlite://",
    ),
    "REDIS_URL": (
        re.compile(r"^rediss?://"),
        "must start with redis:// or rediss://",
    ),
}

_PRODUCTION_MARKERS = (
    "PRODUCTION",
    "PROD",
    "RENDER",
)


def _is_production() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "").upper()
    if env in _PRODUCTION_MARKERS:
        return True
    if os.getenv("RENDER"):
        return True
    if os.getenv("PRODUCTION") == "true":
        return True
    return False


def _missing(vars_):
    return [name for name in vars_ if not os.getenv(name)]


def validate_environment(exit_on_failure=True):
    problems = []

    missing = _missing(_REQUIRED_ALWAYS)
    if missing:
        problems.append(
            "Missing required environment variables: " + ", ".join(missing)
        )

    if _is_production():
        missing_prod = _missing(_REQUIRED_IN_PRODUCTION)
        if missing_prod:
            problems.append(
                "Missing production environment variables: "
                + ", ".join(missing_prod)
            )

    for name, (pattern, hint) in _PATTERN_VALIDATORS.items():
        value = os.getenv(name)
        if value and not pattern.match(value):
            problems.append(f"{name} {hint} (got: {value[:20]}...)")

    if not problems:
        return

    message = "Configuration error(s):\\n  - " + "\\n  - ".join(problems)
    print(message, file=sys.stderr)

    if exit_on_failure and _is_production():
        sys.exit(1)
    if exit_on_failure:
        print(
            "Continuing in non-production mode. Fix the above before deploying.",
            file=sys.stderr,
        )


def get_required(name):
    value = os.getenv(name)
    if not value:
        raise ConfigError(f"Environment variable {name} is required but not set.")
    return value


def get_optional(name, default=""):
    return os.getenv(name, default)
'''

FILES["logging_config.py"] = '''"""Structured JSON logging for the API.

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
            base += "\\n" + self.formatException(record.exc_info)
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
'''

FILES["error_handler.py"] = '''"""Global exception handling.

Catches anything raised inside request handlers or background tasks and returns
a consistent JSON error envelope. Logs full stack traces server-side without
leaking internals to clients.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected application errors."""

    def __init__(self, message, status_code=400, code="app_error", extra=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.extra = extra or {}


class NotFoundError(AppError):
    def __init__(self, message="Not found", **kw):
        super().__init__(message, status_code=404, code="not_found", **kw)


class AuthError(AppError):
    def __init__(self, message="Unauthorized", **kw):
        super().__init__(message, status_code=401, code="unauthorized", **kw)


class ForbiddenError(AppError):
    def __init__(self, message="Forbidden", **kw):
        super().__init__(message, status_code=403, code="forbidden", **kw)


class ValidationError(AppError):
    def __init__(self, message="Invalid input", **kw):
        super().__init__(message, status_code=422, code="validation_error", **kw)


def _envelope(code, message, request_id=None, extra=None):
    body = {"error": {"code": code, "message": message}}
    if request_id:
        body["error"]["request_id"] = request_id
    if extra:
        body["error"].update(extra)
    return body


def install_error_handlers(app: FastAPI):
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError):
        rid = getattr(request.state, "request_id", None)
        logger.warning("AppError %s: %s", exc.code, exc.message,
                       extra={"request_id": rid})
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, rid, exc.extra),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope("http_error", str(exc.detail), rid),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content=_envelope("validation_error", "Invalid request", rid,
                              {"fields": exc.errors()}),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception):
        rid = getattr(request.state, "request_id", None)
        logger.exception("Unhandled exception", extra={"request_id": rid})
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error",
                              "Something went wrong. Please try again.", rid),
        )
'''

FILES["health.py"] = '''"""Health and readiness endpoints.

/health  - liveness: process is up
/ready   - readiness: dependencies (DB, Redis) reachable
/metrics - lightweight runtime counters
"""
from __future__ import annotations

import os
import time

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(tags=["health"])

_STARTED_AT = time.time()
_COUNTERS = {"requests": 0}


def _db_check():
    try:
        from .db import SessionLocal
        session = SessionLocal()
        try:
            session.execute(text("SELECT 1"))
            return {"ok": True}
        finally:
            session.close()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _redis_check():
    url = os.getenv("REDIS_URL")
    if not url:
        return {"ok": True, "skipped": "REDIS_URL not set"}
    try:
        import redis  # type: ignore
        client = redis.from_url(url, socket_connect_timeout=2)
        client.ping()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "version": os.getenv("APP_VERSION", "dev"),
    }


@router.get("/ready")
async def ready():
    db = _db_check()
    redis = _redis_check()
    ok = db.get("ok") and redis.get("ok")
    return {
        "status": "ready" if ok else "not_ready",
        "checks": {"db": db, "redis": redis},
    }


@router.get("/metrics")
async def metrics():
    return {
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
        "requests_total": _COUNTERS["requests"],
    }
'''

FILES["middleware.py"] = '''"""Request middleware.

Assigns a request ID to every request, logs start/end with duration, and adds
the request ID to the response headers so clients can correlate.
"""
from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

from .logging_config import new_request_id

logger = logging.getLogger("api.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or new_request_id()
        request.state.request_id = rid
        started = time.time()

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.time() - started) * 1000)
            logger.exception(
                "request failed",
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                },
            )
            raise

        duration_ms = int((time.time() - started) * 1000)
        response.headers["x-request-id"] = rid
        if not request.url.path.startswith(("/health", "/ready", "/metrics")):
            logger.info(
                "request",
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response
'''


def write_file(name, content):
    path = BASE / name
    path.write_text(content, encoding="utf-8")
    print("Created: %s (%d bytes)" % (name, len(content)))


def main():
    for name, content in FILES.items():
        write_file(name, content)
    print()
    print("Phase A complete. %d files created in %s" % (len(FILES), BASE))


if __name__ == "__main__":
    main()