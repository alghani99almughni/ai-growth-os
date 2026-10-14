"""Public QR-first visitor request endpoint backed by the existing SmartCheck bridge.

This endpoint intentionally does not write visitor records into the AI Growth OS SQL
visitor tables. It requires an explicit tenant mapping and server-side bridge secret.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import Tenant
from .models_growth import TenantSetting, PlatformSetting

router = APIRouter(prefix="/api/v1/public/smartcheck", tags=["public-smartcheck-visitors"])
_ALLOWED_SCRIPT_HOSTS = {"script.google.com", "script.googleusercontent.com"}


class PublicVisitorRequest(BaseModel):
    visitor_name: str = Field(min_length=1, max_length=160)
    visitor_mobile: str = Field(min_length=5, max_length=32)
    purpose: str = Field(default="", max_length=240)
    destination: str = Field(default="", max_length=200)
    vehicle_number: str = Field(default="", max_length=40)


class GoogleScriptRedirectHandler(HTTPRedirectHandler):
    """Allow normal Apps Script redirects without allowing redirects to arbitrary hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_SCRIPT_HOSTS:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _tenant_feature_enabled(db, tenant_id: str) -> bool:
    feature_row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id, TenantSetting.key == "features"
    ))
    defaults_row = db.scalar(select(PlatformSetting).where(PlatformSetting.key == "feature_defaults"))
    try:
        features = json.loads(feature_row.value_json) if feature_row else {}
    except (TypeError, ValueError):
        features = {}
    try:
        defaults = json.loads(defaults_row.value_json) if defaults_row else {}
    except (TypeError, ValueError):
        defaults = {}
    return bool(features.get("security_visitor_management",
                             defaults.get("security_visitor_management", False)))


def _script_config(db, tenant_id: str) -> dict:
    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id, TenantSetting.key == "smartcheck_connection"
    ))
    try:
        config = json.loads(row.value_json) if row else {}
    except (TypeError, ValueError):
        config = {}
    script_url = str(config.get("script_url", "")).strip()
    parsed = urlparse(script_url)
    if (parsed.scheme != "https" or parsed.hostname != "script.google.com"
            or parsed.username or parsed.password or not parsed.path.startswith("/macros/s/")
            or not parsed.path.endswith("/exec") or parsed.query or parsed.fragment):
        raise HTTPException(503, "SmartCheck visitor registration is not configured for this tenant")
    if not str(config.get("legacy_tenant_code", "")).strip():
        raise HTTPException(503, "SmartCheck tenant mapping is not configured for this tenant")
    if not os.getenv("AI_GROWTH_OS_BRIDGE_SECRET", "").strip():
        raise HTTPException(503, "SmartCheck bridge credentials are not configured")
    return config


def _require_lifecycle_ready(config: dict) -> None:
    # A public request must not enter Sheets until the same system can list and
    # approve it, record gate transitions, and verify its QR/pass state.
    if config.get("visitor_lifecycle_sync_ready") is not True:
        raise HTTPException(
            503,
            "Visitor registration is not enabled until SmartCheck listing, approval, gate transitions, and QR verification are synchronized",
        )


def _submit_to_smartcheck(config: dict, secret: str, body: PublicVisitorRequest) -> dict:
    tenant_code = str(config["legacy_tenant_code"]).strip()
    payload = {
        "action": "VISITOR_REQUEST",
        "bridgeSecret": secret,
        "actorRole": "VISITOR",
        "actorTenantId": tenant_code,
        "tenantId": tenant_code,
        "visitorName": body.visitor_name.strip(),
        "visitorMobile": body.visitor_mobile.strip(),
        "purpose": body.purpose.strip(),
        "targetDestination": body.destination.strip(),
        "vehicleNumber": body.vehicle_number.strip().upper(),
    }
    request = Request(
        str(config["script_url"]).strip(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "AI-Growth-OS-SmartCheck/1.0"},
        method="POST",
    )
    opener = build_opener(GoogleScriptRedirectHandler())
    try:
        with opener.open(request, timeout=10) as response:
            final = urlparse(response.geturl())
            if final.scheme != "https" or final.hostname not in _ALLOWED_SCRIPT_HOSTS:
                raise HTTPException(502, "SmartCheck returned an untrusted redirect")
            raw = response.read(65536)
        result = json.loads(raw.decode("utf-8"))
    except HTTPException:
        raise
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        raise HTTPException(502, "SmartCheck could not accept the visitor request") from None
    if not isinstance(result, dict) or result.get("status") != "success" or not result.get("ticketId"):
        raise HTTPException(502, "SmartCheck did not confirm that the visitor request was saved")
    return {
        "ticket_id": str(result["ticketId"]),
        "status": str(result.get("statusLabel", "PENDING")),
        "message": "Visitor request submitted. Entry is not permitted until an authorized person approves it.",
    }


@router.post("/{tenant_slug}/visitor-requests")
def create_public_visitor_request(tenant_slug: str, body: PublicVisitorRequest):
    """Public QR visitor form; request is saved to SmartCheck and remains pending approval."""
    db = SessionLocal()
    try:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug.lower()))
        if not tenant or str(tenant.status).lower() not in {"active", "trial"}:
            raise HTTPException(404, "Visitor registration is unavailable for this tenant")
        if not _tenant_feature_enabled(db, tenant.id):
            raise HTTPException(403, "Security & Visitor Management is disabled for this tenant")
        config = _script_config(db, tenant.id)
        _require_lifecycle_ready(config)
    finally:
        db.close()
    return _submit_to_smartcheck(config, os.environ["AI_GROWTH_OS_BRIDGE_SECRET"], body)
