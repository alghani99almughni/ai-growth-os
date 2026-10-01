"""Multi-channel WhatsApp manager.

A tenant can have TWO independent WhatsApp connections at the same time:
    - OpenWA (platform-hosted)
    - Meta  (tenant brings their own Cloud API keys)

Each channel is stored as its own row in TenantWhatsAppConnection, keyed by
(tenant_id, provider). The tenant's preferred channel is stored in
TenantSetting key "whatsapp_priority" and defaults to "openwa".

This module is the single source of truth for:
    - Reading a tenant's channel state (for the settings UI)
    - Configuring or disconnecting one channel at a time
    - Picking the adapter to use for outbound (with automatic failover)
    - Picking the adapter for inbound (the channel the message came in on)

Nothing in here changes WhatsAppAdapter itself. The adapter still works
exactly as it does today.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


CHANNEL_PROVIDERS = ("openwa", "meta")
DEFAULT_PRIORITY = "openwa"


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------

def get_priority(db: Session, tenant_id: str) -> str:
    """Return the tenant's preferred outbound channel.

    Falls back to DEFAULT_PRIORITY (openwa) if unset. If the preferred
    channel is not connected, the caller can use `active_adapter` which
    handles that fallback automatically.
    """
    try:
        from .models_growth import TenantSetting
        row = db.scalar(select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id,
            TenantSetting.key == "whatsapp_priority",
        ))
        if not row:
            return DEFAULT_PRIORITY
        data = json.loads(row.value_json or "{}")
        val = str(data.get("priority") or DEFAULT_PRIORITY).lower()
        return val if val in CHANNEL_PROVIDERS else DEFAULT_PRIORITY
    except Exception:
        return DEFAULT_PRIORITY


def set_priority(db: Session, tenant_id: str, priority: str) -> str:
    """Persist the tenant's preferred channel. Returns the stored value."""
    p = (priority or "").strip().lower()
    if p not in CHANNEL_PROVIDERS:
        raise ValueError("priority must be 'openwa' or 'meta'")
    from .models_growth import TenantSetting
    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == "whatsapp_priority",
    ))
    payload = json.dumps({"priority": p})
    if row:
        row.value_json = payload
    else:
        db.add(TenantSetting(
            id=str(secrets.token_hex(18)),
            tenant_id=tenant_id,
            key="whatsapp_priority",
            value_json=payload,
        ))
    db.commit()
    return p


# ---------------------------------------------------------------------------
# Channel state
# ---------------------------------------------------------------------------

def _row_for(db: Session, tenant_id: str, provider: str):
    from .models import TenantWhatsAppConnection
    return db.scalar(select(TenantWhatsAppConnection).where(
        TenantWhatsAppConnection.tenant_id == tenant_id,
        TenantWhatsAppConnection.provider == provider,
    ))


def channel_status(db: Session, tenant_id: str, provider: str) -> dict:
    """Return the status of one channel for the settings UI."""
    row = _row_for(db, tenant_id, provider)
    if not row or not row.config_encrypted:
        return {
            "provider": provider,
            "connected": False,
            "status": "disconnected",
            "connected_phone": None,
            "display_name": None,
        }
    return {
        "provider": row.provider,
        "connected": row.status == "connected",
        "status": row.status,
        "connected_phone": row.connected_phone,
        "display_name": row.display_name,
    }


def all_channels(db: Session, tenant_id: str) -> dict:
    """Return state for both channels plus the current priority.

    Shape:
        {
            "openwa": {provider, connected, status, connected_phone, display_name},
            "meta":   {...},
            "priority": "openwa" | "meta",
            "active": "openwa" | "meta" | None,
        }
    """
    openwa = channel_status(db, tenant_id, "openwa")
    meta = channel_status(db, tenant_id, "meta")
    priority = get_priority(db, tenant_id)

    # Compute which channel would actually be used right now
    active = None
    if priority == "openwa":
        if openwa["connected"]:
            active = "openwa"
        elif meta["connected"]:
            active = "meta"
    else:
        if meta["connected"]:
            active = "meta"
        elif openwa["connected"]:
            active = "openwa"

    return {"openwa": openwa, "meta": meta, "priority": priority, "active": active}


# ---------------------------------------------------------------------------
# Configure / disconnect
# ---------------------------------------------------------------------------

def configure_channel(
    db: Session,
    tenant_id: str,
    provider: str,
    config: dict,
    connected_phone: Optional[str],
    display_name: Optional[str],
) -> dict:
    """Upsert the config for a single provider.

    config must already be validated by the caller. It will be encrypted
    here using the platform's WhatsApp credential key.
    """
    from .models import TenantWhatsAppConnection
    from .integrations import encrypt_channel_config
    from .config import settings

    if provider not in CHANNEL_PROVIDERS:
        raise ValueError("unsupported provider")

    row = _row_for(db, tenant_id, provider)
    if not row:
        row = TenantWhatsAppConnection(
            id=secrets.token_hex(18),
            tenant_id=tenant_id,
            provider=provider,
        )
        db.add(row)

    row.provider = provider
    row.status = "connected"
    row.config_encrypted = encrypt_channel_config(
        {"provider": provider, **config},
        settings.whatsapp_credential_encryption_key,
    )
    row.connected_phone = connected_phone
    row.display_name = display_name
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return channel_status(db, tenant_id, provider)


def disconnect_channel(db: Session, tenant_id: str, provider: str) -> dict:
    """Mark a single channel as disconnected without affecting the other."""
    if provider not in CHANNEL_PROVIDERS:
        raise ValueError("unsupported provider")
    row = _row_for(db, tenant_id, provider)
    if row:
        row.status = "disconnected"
        row.config_encrypted = ""
        row.connected_phone = None
        row.display_name = None
        row.updated_at = datetime.utcnow()
        db.commit()
    return channel_status(db, tenant_id, provider)


# ---------------------------------------------------------------------------
# Adapter selection
# ---------------------------------------------------------------------------

def adapter_for_channel(db: Session, tenant_id: str, provider: str, settings_obj):
    """Build the WhatsAppAdapter for one specific provider, or return None
    if that provider is not connected for this tenant."""
    from .integrations import whatsapp_adapter_from_config, decrypt_channel_config
    row = _row_for(db, tenant_id, provider)
    if not row or not row.config_encrypted or row.status != "connected":
        return None
    try:
        cfg = decrypt_channel_config(
            row.config_encrypted,
            settings_obj.whatsapp_credential_encryption_key,
        )
        return whatsapp_adapter_from_config(cfg)
    except Exception as exc:
        logger.warning("adapter_for_channel failed tenant=%s provider=%s: %s",
                       tenant_id, provider, exc)
        return None


def active_adapter(db: Session, tenant_id: str, settings_obj):
    """Return the adapter to use for outbound messages.

    Returns (adapter, channel_name) where channel_name is one of
    "openwa" or "meta". Returns (None, None) if no channel is connected.

    Respects the tenant's priority setting. Falls back to the other
    channel if the preferred one is not connected.
    """
    priority = get_priority(db, tenant_id)
    other = "meta" if priority == "openwa" else "openwa"

    first = adapter_for_channel(db, tenant_id, priority, settings_obj)
    if first is not None:
        return first, priority

    second = adapter_for_channel(db, tenant_id, other, settings_obj)
    if second is not None:
        return second, other

    return None, None


def fallback_adapter(db: Session, tenant_id: str, exclude: str, settings_obj):
    """Return the other channel's adapter, for send-failover.

    Returns (adapter, channel_name) or (None, None).
    """
    other = "meta" if exclude == "openwa" else "openwa"
    adapter = adapter_for_channel(db, tenant_id, other, settings_obj)
    if adapter is not None:
        return adapter, other
    return None, None


# ---------------------------------------------------------------------------
# Outbound send with failover
# ---------------------------------------------------------------------------

async def send_text_with_failover(db: Session, tenant_id: str, settings_obj, phone: str, text: str) -> dict:
    """Send a WhatsApp text message, trying the primary channel first.

    Returns a dict:
        {"ok": bool, "channel": "openwa"|"meta"|None, "error": str|None,
         "fell_back": bool}
    """
    primary, primary_name = active_adapter(db, tenant_id, settings_obj)
    if primary is None:
        return {"ok": False, "channel": None, "error": "no_channel_connected", "fell_back": False}

    try:
        result = await primary.send_text(phone, text)
        return {"ok": True, "channel": primary_name, "error": None,
                "fell_back": False, "provider_response": result}
    except Exception as exc:
        logger.warning("primary send failed tenant=%s channel=%s: %s",
                       tenant_id, primary_name, exc)

    fallback, fallback_name = fallback_adapter(db, tenant_id, primary_name, settings_obj)
    if fallback is None:
        return {"ok": False, "channel": primary_name, "error": "primary_failed_no_fallback",
                "fell_back": False}

    try:
        result = await fallback.send_text(phone, text)
        return {"ok": True, "channel": fallback_name, "error": None,
                "fell_back": True, "provider_response": result}
    except Exception as exc:
        return {"ok": False, "channel": fallback_name,
                "error": f"both_channels_failed: {exc}", "fell_back": True}