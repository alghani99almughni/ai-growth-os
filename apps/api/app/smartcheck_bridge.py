"""Authenticated adapter for the existing SmartCheck Apps Script / Sheets source of truth.

This module never exposes the bridge secret to the browser. It deliberately fails closed
unless the tenant connection explicitly marks the full visitor lifecycle as ready.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import HTTPException
from sqlalchemy import select

from .models_growth import TenantSetting

_ALLOWED_HOSTS = {"script.google.com", "script.googleusercontent.com"}
_STATUS = {
    "PENDING": "pending",
    "APPROVED": "approved",
    "REJECTED": "denied",
    "CHECKED_IN": "checked_in",
    "CHECKED_OUT": "checked_out",
    "EXPIRED": "expired",
    "CANCELLED": "cancelled",
}


def lifecycle_config(db, tenant_id: str) -> dict | None:
    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id, TenantSetting.key == "smartcheck_connection"
    ))
    try:
        cfg = json.loads(row.value_json) if row else {}
    except (TypeError, ValueError):
        cfg = {}
    if cfg.get("visitor_lifecycle_sync_ready") is not True:
        return None
    url = str(cfg.get("script_url", "")).strip()
    parsed = urlparse(url)
    if (parsed.scheme != "https" or parsed.hostname != "script.google.com"
            or parsed.username or parsed.password or not parsed.path.startswith("/macros/s/")
            or not parsed.path.endswith("/exec") or parsed.query or parsed.fragment
            or not str(cfg.get("legacy_tenant_code", "")).strip()):
        raise HTTPException(503, "SmartCheck lifecycle connection is invalid")
    if not os.getenv("AI_GROWTH_OS_BRIDGE_SECRET", "").strip():
        raise HTTPException(503, "SmartCheck bridge credentials are not configured")
    return cfg


class _SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_HOSTS:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def call_smartcheck(config: dict, user, action: str, **fields) -> dict:
    secret = os.getenv("AI_GROWTH_OS_BRIDGE_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "SmartCheck bridge credentials are not configured")
    tenant_code = str(config.get("legacy_tenant_code", "")).strip()
    role = str(getattr(user.role, "value", user.role) or "").strip().upper().replace("-", "_").replace(" ", "_")
    role = {"ADMIN": "TENANT_ADMIN", "MANAGER": "TENANT_ADMIN", "GUARD": "SECURITY", "SECURITY_GUARD": "SECURITY"}.get(role, role)
    payload = {
        "action": action,
        "bridgeSecret": secret,
        "actorRole": role,
        "actorTenantId": tenant_code,
        "tenantId": tenant_code,
        "actorEmail": str(getattr(user, "email", "") or getattr(user, "name", "") or getattr(user, "id", "AI Growth OS")),
        **fields,
    }
    request = Request(
        str(config["script_url"]).strip(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "AI-Growth-OS-SmartCheck/1.0"},
        method="POST",
    )
    try:
        with build_opener(_SafeRedirect()).open(request, timeout=12) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in _ALLOWED_HOSTS:
                raise HTTPException(502, "SmartCheck returned an untrusted redirect")
            result = json.loads(response.read(262144).decode("utf-8"))
    except HTTPException:
        raise
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        raise HTTPException(502, "SmartCheck could not complete the visitor action") from None
    if not isinstance(result, dict) or result.get("status") not in {"success", "ok"}:
        raise HTTPException(502, str(result.get("message", "SmartCheck rejected the visitor action"))[:240] if isinstance(result, dict) else "SmartCheck returned an invalid response")
    return result


def pass_from_sheet(row: dict, tenant_id: str) -> dict:
    status = _STATUS.get(str(row.get("Status", "")).strip().upper(), "pending")
    return {
        "id": str(row.get("Ticket ID", "")),
        "tenant_id": tenant_id,
        "site_id": None,
        "visitor_name": str(row.get("Visitor Name", "")),
        "visitor_mobile": str(row.get("Mobile", "")),
        "purpose": str(row.get("Purpose", "")),
        "destination": str(row.get("Target Destination", "")),
        "vehicle_number": str(row.get("Vehicle Number", "")),
        "industry": "apartment",
        "status": status,
        "expires_at": None,
        "created_at": str(row.get("Date", "")) or None,
        "checked_in_at": str(row.get("Updated At", "")) or None if status == "checked_in" else None,
        "checked_out_at": str(row.get("Updated At", "")) or None if status == "checked_out" else None,
        "qr_token": str(row.get("QR Token", "")) or None,
    }
