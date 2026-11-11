"""Health and readiness endpoints.

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
