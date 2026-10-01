"""Production hardening helpers.

Provides:
    - SecurityHeadersMiddleware  (HSTS, CSP, X-Frame-Options, etc.)
    - RequestSizeLimitMiddleware (reject oversized bodies early)
    - auth_rate_limit()          (per-IP + per-email rate limit for auth routes)
    - enrich_health()            (DB, Redis, TURN, cleanup status)
    - install_signal_handlers()  (graceful shutdown on SIGTERM)

Nothing here changes existing endpoint behavior. It only adds protective
layers around them.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("api.hardening")


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response.

    CSP is intentionally permissive for the API because the API serves JSON
    only, not HTML. If you add HTML-rendering routes (e.g. docs), tighten
    default-src accordingly.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # HSTS only makes sense over HTTPS. In dev (http://localhost) it
        # can lock users out of localhost in Chrome. So gate on env.
        env = os.getenv("ENVIRONMENT", "development").lower()
        if env == "production":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; frame-ancestors 'none'",
        )
        return response


# ---------------------------------------------------------------------------
# Request size limit
# ---------------------------------------------------------------------------

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject request bodies larger than MAX_REQUEST_BYTES (default 2 MB).

    Reads Content-Length header if present. Streams otherwise are not
    wrapped — most routes are JSON, so Content-Length is nearly always set.
    """

    def __init__(self, app, max_bytes: int = 2 * 1024 * 1024):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length")
        if cl:
            try:
                if int(cl) > self.max_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"error": {"code": "payload_too_large",
                                           "message": f"Request body exceeds {self.max_bytes} bytes"}},
                    )
            except ValueError:
                pass
        return await call_next(request)


# ---------------------------------------------------------------------------
# Auth rate limit (per IP + per email)
# ---------------------------------------------------------------------------

_AUTH_BUCKETS: dict = defaultdict(list)
_AUTH_LOCK = asyncio.Lock()

AUTH_WINDOW_SECONDS = 15 * 60     # 15 minutes
AUTH_MAX_PER_IP = 20              # 20 attempts per IP per window
AUTH_MAX_PER_EMAIL = 10           # 10 attempts per email per window


async def auth_rate_limit(request: Request, email: str | None = None) -> None:
    """Raise 429 if the caller exceeds auth attempt limits.

    Call at the top of /login, /register, /password-reset/request.
    """
    now = time.time()
    client = request.client.host if request.client else "unknown"
    ip_key = ("ip", client)
    email_key = ("email", (email or "").lower().strip()) if email else None

    async with _AUTH_LOCK:
        # prune old entries
        for key in (ip_key, email_key):
            if not key:
                continue
            bucket = _AUTH_BUCKETS[key]
            cutoff = now - AUTH_WINDOW_SECONDS
            _AUTH_BUCKETS[key] = [t for t in bucket if t >= cutoff]

        # check limits
        ip_count = len(_AUTH_BUCKETS[ip_key])
        if ip_count >= AUTH_MAX_PER_IP:
            logger.warning("auth rate limit hit: ip=%s count=%d", client, ip_count)
            raise HTTPException(429, "Too many attempts from this address. Try again in 15 minutes.")

        if email_key:
            email_count = len(_AUTH_BUCKETS[email_key])
            if email_count >= AUTH_MAX_PER_EMAIL:
                logger.warning("auth rate limit hit: email=%s count=%d",
                               email_key[1], email_count)
                raise HTTPException(429, "Too many attempts for this account. Try again in 15 minutes.")

        # record this attempt
        _AUTH_BUCKETS[ip_key].append(now)
        if email_key:
            _AUTH_BUCKETS[email_key].append(now)


def auth_rate_limit_status() -> dict:
    """Diagnostic: how many buckets are active."""
    now = time.time()
    active = sum(1 for k, v in _AUTH_BUCKETS.items()
                 if any(t >= now - AUTH_WINDOW_SECONDS for t in v))
    return {"active_buckets": active, "tracked_keys": len(_AUTH_BUCKETS)}


# ---------------------------------------------------------------------------
# Enriched health
# ---------------------------------------------------------------------------

def enrich_health() -> dict:
    """Return a health snapshot with DB, Redis, TURN, and cleanup status."""
    out = {
        "status": "ok",
        "service": "ai-growth-os-api",
        "time": datetime.utcnow().isoformat() + "Z",
        "checks": {},
    }

    # Database
    try:
        from .db import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            out["checks"]["database"] = {"ok": True}
        finally:
            db.close()
    except Exception as exc:
        out["checks"]["database"] = {"ok": False, "error": str(exc)[:200]}
        out["status"] = "degraded"

    # Redis (optional)
    try:
        from .config import settings
        if settings.redis_url:
            import redis  # type: ignore
            r = redis.Redis.from_url(settings.redis_url, socket_timeout=2)
            r.ping()
            out["checks"]["redis"] = {"ok": True}
            r.close()
        else:
            out["checks"]["redis"] = {"ok": True, "note": "not configured"}
    except Exception as exc:
        out["checks"]["redis"] = {"ok": False, "error": str(exc)[:200], "note": "non-fatal; local signaling fallback active"}

    # TURN config
    try:
        from .turn import turn_config_status
        turn = turn_config_status()
        out["checks"]["turn"] = {
            "ok": True,
            "primary": turn.get("primary"),
            "fallback": turn.get("fallback"),
            "cloudflare_configured": turn.get("cloudflare_configured"),
            "metered_configured": turn.get("metered_configured"),
        }
    except Exception as exc:
        out["checks"]["turn"] = {"ok": False, "error": str(exc)[:200]}

    # Encryption keys
    try:
        from .config import settings
        out["checks"]["encryption"] = {
            "ok": bool(settings.whatsapp_credential_encryption_key
                       and settings.integration_credential_encryption_key),
            "whatsapp_key_set": bool(settings.whatsapp_credential_encryption_key),
            "integration_key_set": bool(settings.integration_credential_encryption_key),
        }
        if not out["checks"]["encryption"]["ok"]:
            out["status"] = "degraded"
    except Exception as exc:
        out["checks"]["encryption"] = {"ok": False, "error": str(exc)[:200]}

    # Auth rate limiter
    try:
        from .hardening import auth_rate_limit_status
        out["checks"]["auth_rate_limit"] = auth_rate_limit_status()
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------

def install_signal_handlers(app) -> None:
    """Close DB pool and Redis on SIGTERM. Render sends SIGTERM on deploy.

    Second SIGTERM forces an immediate exit so a stuck process cannot loop.
    """
    _shutting_down = {"v": False}

    def _shutdown(signum=None, frame=None):
        if _shutting_down["v"]:
            import sys as _sys
            _sys.exit(1)
        _shutting_down["v"] = True
        logger.info("SIGTERM received - closing resources")
        try:
            from .db import engine
            engine.dispose()
            logger.info("DB engine disposed")
        except Exception as exc:
            logger.debug("engine.dispose failed: %s", exc)
        try:
            from .config import settings
            if settings.redis_url:
                import redis
                redis.Redis.from_url(settings.redis_url).close()
        except Exception:
            pass
        import sys as _sys
        _sys.exit(0)

    import signal as _sig
    for sig in (_sig.SIGTERM, _sig.SIGINT):
        try:
            _sig.signal(sig, _shutdown)
        except Exception:
            pass

