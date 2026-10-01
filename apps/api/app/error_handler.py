"""Global exception handling.

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
