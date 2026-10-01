"""TURN credential generation — Cloudflare + Metered.

Both providers issue short-lived credentials via a REST API. The backend
calls the provider, gets back a username/password pair, and passes them to
the browser. Credentials expire, so a leaked response is not a permanent
grant.

Config source priority:
    1. app.config.settings (pydantic, reads .env locally)
    2. os.getenv (falls back to OS environment, used by Render and Docker)

Providers:
    TURN_PROVIDER              "cloudflare" | "metered" (default: cloudflare)
    TURN_PROVIDER_FALLBACK     optional second provider to try on failure

Cloudflare:
    CLOUDFLARE_TURN_KEY_ID
    CLOUDFLARE_TURN_API_TOKEN

Metered:
    METERED_APP_NAME           e.g. "sappz" from sappz.metered.live
    METERED_SECRET_KEY

If no provider is configured, returns STUN-only. Direct P2P still works;
TURN relay is skipped. Nothing breaks.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


DEFAULT_TTL_SECONDS = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Config reader — settings first, os.getenv fallback
# ---------------------------------------------------------------------------

def _cfg(name: str, default: str = "") -> str:
    """Read a config value from pydantic settings, fall back to OS env.

    Both paths are checked because:
        - Local dev: pydantic reads .env
        - Render/Docker: values come in as OS environment variables
        - Tests: may set either
    """
    try:
        from .config import settings
        val = getattr(settings, name.lower(), None)
        if val is not None and val != "":
            return str(val)
    except Exception:
        pass
    return os.getenv(name, default) or default


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class IceConfig:
    ok: bool
    ice_servers: list = field(default_factory=list)
    provider: Optional[str] = None
    ttl_seconds: int = 0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def generate_ice_config(
    *,
    tenant_id: str = "",
    user_id: str = "",
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> IceConfig:
    """Return ICE servers with short-lived TURN credentials."""
    primary = (_cfg("TURN_PROVIDER") or "cloudflare").strip().lower()
    fallback = (_cfg("TURN_PROVIDER_FALLBACK") or "").strip().lower() or None

    for provider in (primary, fallback):
        if not provider:
            continue
        result = await _try_provider(provider, tenant_id, user_id, ttl_seconds)
        if result.ok:
            return result
        logger.warning("TURN provider %s failed: %s", provider, result.error)

    return IceConfig(
        ok=True,
        provider=None,
        ttl_seconds=0,
        ice_servers=[
            {"urls": "stun:stun.l.google.com:19302"},
            {"urls": "stun:stun1.l.google.com:19302"},
        ],
        error="turn_unavailable",
    )


async def _try_provider(provider: str, tenant_id: str, user_id: str, ttl: int) -> IceConfig:
    if provider == "cloudflare":
        return await _cloudflare_ice(tenant_id, user_id, ttl)
    if provider == "metered":
        return await _metered_ice(tenant_id, user_id, ttl)
    return IceConfig(ok=False, error=f"unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Cloudflare
# ---------------------------------------------------------------------------

async def _cloudflare_ice(tenant_id: str, user_id: str, ttl: int) -> IceConfig:
    key_id = _cfg("CLOUDFLARE_TURN_KEY_ID")
    token = _cfg("CLOUDFLARE_TURN_API_TOKEN")
    if not key_id or not token:
        return IceConfig(ok=False, error="cloudflare_not_configured")

    url = (
        f"https://rtc.live.cloudflare.com/v1/turn/keys/{key_id}"
        f"/credentials/generate-ice-servers"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"ttl": ttl},
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        return IceConfig(ok=False, error=f"cloudflare_request_failed: {exc}")

    servers = data.get("iceServers")
    if not servers:
        return IceConfig(ok=False, error="cloudflare_empty_response")
    if isinstance(servers, dict):
        servers = [servers]

    return IceConfig(ok=True, ice_servers=servers, provider="cloudflare", ttl_seconds=ttl)


# ---------------------------------------------------------------------------
# Metered
# ---------------------------------------------------------------------------

async def _metered_ice(tenant_id: str, user_id: str, ttl: int) -> IceConfig:
    app_name = _cfg("METERED_APP_NAME")
    secret_key = _cfg("METERED_SECRET_KEY")
    if not app_name or not secret_key:
        return IceConfig(ok=False, error="metered_not_configured")

    label = f"tenant-{tenant_id[:8]}" if tenant_id else "default"
    create_url = (
        f"https://{app_name}.metered.live/api/v2/turn/credential"
        f"?secretKey={secret_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                create_url,
                json={"expiryInSeconds": ttl, "label": label},
            )
            r.raise_for_status()
            cred = r.json()
    except Exception as exc:
        return IceConfig(ok=False, error=f"metered_create_failed: {exc}")

    username = cred.get("username")
    password = cred.get("password")
    if not username or not password:
        return IceConfig(ok=False, error="metered_empty_credential")

    api_key = cred.get("apiKey")
    if not api_key:
        return IceConfig(ok=False, error="metered_missing_api_key")

    fetch_url = (
        f"https://{app_name}.metered.live/api/v1/turn/credentials"
        f"?apiKey={api_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(fetch_url)
            r.raise_for_status()
            servers = r.json()
    except Exception as exc:
        return IceConfig(ok=False, error=f"metered_fetch_failed: {exc}")

    if not isinstance(servers, list) or not servers:
        return IceConfig(ok=False, error="metered_empty_servers")

    return IceConfig(ok=True, ice_servers=servers, provider="metered", ttl_seconds=ttl)


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

def turn_config_status() -> dict:
    """Return which providers are configured, for health diagnostics."""
    primary = (_cfg("TURN_PROVIDER") or "cloudflare").strip().lower()
    fallback = (_cfg("TURN_PROVIDER_FALLBACK") or "").strip().lower() or None
    return {
        "primary": primary,
        "fallback": fallback,
        "cloudflare_configured": bool(
            _cfg("CLOUDFLARE_TURN_KEY_ID") and _cfg("CLOUDFLARE_TURN_API_TOKEN")
        ),
        "metered_configured": bool(
            _cfg("METERED_APP_NAME") and _cfg("METERED_SECRET_KEY")
        ),
    }