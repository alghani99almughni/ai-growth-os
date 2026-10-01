"""Request middleware.

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
