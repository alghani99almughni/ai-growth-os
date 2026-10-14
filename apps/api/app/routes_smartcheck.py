"""Platform-managed SmartCheck connection diagnostics.

A successful HEALTH response proves only that the Apps Script deployment is reachable.
It does not prove bridge authentication, tenant mapping, or Drive access.
"""
from __future__ import annotations

import json
import secrets
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import Tenant, User
from .models_growth import TenantSetting
from .security import decode_token_strict
from .smartcheck_bridge import call_smartcheck

router = APIRouter(prefix="/api/v1/platform/tenants", tags=["smartcheck-connections"])
PLATFORM_ROLES = {"platform_admin", "super_admin"}


def normalized_role(value) -> str:
    """Normalize both string roles and Enum-backed roles consistently."""
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def platform_user(authorization: str | None = Header(default=None), db: Session = Depends(db_session)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token required")
    try:
        payload = decode_token_strict(authorization.split(" ", 1)[1], settings.jwt_secret, settings.jwt_algorithm)
    except Exception:
        raise HTTPException(401, "Invalid access token")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active or normalized_role(user.role) not in PLATFORM_ROLES:
        raise HTTPException(403, "Platform administrator permission required")
    return user


class SmartCheckConnectionInput(BaseModel):
    script_url: str = Field(min_length=1, max_length=1000)
    drive_folder_url: str | None = Field(default=None, max_length=1000)
    legacy_tenant_code: str | None = Field(default=None, max_length=100)


def validate_legacy_tenant_code(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    code = value.strip()
    if not all(char.isalnum() or char in "-_" for char in code):
        raise HTTPException(422, "Legacy SmartCheck tenant code may contain only letters, numbers, hyphens, and underscores")
    return code


def validate_script_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname != "script.google.com" or parsed.username or parsed.password:
        raise HTTPException(422, "Use the HTTPS Google Apps Script Web App URL")
    if not parsed.path.startswith("/macros/s/") or not parsed.path.endswith("/exec") or parsed.query or parsed.fragment:
        raise HTTPException(422, "Expected a deployed Apps Script URL ending in /exec")
    return value.strip()


def validate_drive_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.hostname != "drive.google.com" or parsed.username or parsed.password:
        raise HTTPException(422, "Use a Google Drive folder sharing URL")
    if not parsed.path.startswith("/drive/folders/"):
        raise HTTPException(422, "Expected a Google Drive folder URL")
    return value.strip()


def check_script_health(script_url: str) -> dict:
    request = Request(script_url + "?action=HEALTH", headers={"User-Agent": "AI-Growth-OS-SmartCheck/1.0"})
    try:
        with urlopen(request, timeout=8) as response:
            if response.status != 200:
                return {"status": "unreachable", "detail": "Health endpoint returned a non-200 response"}
            payload = json.loads(response.read(65536).decode("utf-8"))
        healthy = isinstance(payload, dict) and str(payload.get("status", "")).lower() == "ok"
        return {"status": "reachable" if healthy else "unverified", "detail": "Health check passed" if healthy else "Health response was not recognized"}
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return {"status": "unreachable", "detail": "Could not verify the Apps Script health endpoint"}


def connection_setting(db: Session, tenant_id: str):
    return db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == "smartcheck_connection",
    ))


@router.get("/{tenant_id}/smartcheck-connection")
def get_smartcheck_connection(tenant_id: str, user: User = Depends(platform_user), db: Session = Depends(db_session)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    row = connection_setting(db, tenant_id)
    try:
        config = json.loads(row.value_json) if row else {}
    except (TypeError, ValueError):
        config = {}
    return {
        "tenant_id": tenant_id,
        "script_url": config.get("script_url", ""),
        "drive_folder_url": config.get("drive_folder_url", ""),
        "legacy_tenant_code": config.get("legacy_tenant_code", ""),
        "script_status": config.get("script_status", "not_configured"),
        "drive_status": "link_saved_unverified" if config.get("drive_folder_url") else "not_configured",
        "authenticated_sync_ready": False,
        "visitor_lifecycle_sync_ready": config.get("visitor_lifecycle_sync_ready") is True,
        "lifecycle_status": "verified" if config.get("visitor_lifecycle_sync_ready") is True else "not_verified",
        "note": "Drive authorization remains unverified; visitor lifecycle readiness is probed separately.",
    }


@router.post("/{tenant_id}/smartcheck-connection")
def save_smartcheck_connection(tenant_id: str, body: SmartCheckConnectionInput, user: User = Depends(platform_user), db: Session = Depends(db_session)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    script_url = validate_script_url(body.script_url)
    drive_url = validate_drive_url(body.drive_folder_url)
    legacy_code = validate_legacy_tenant_code(body.legacy_tenant_code)
    if legacy_code:
        rows = db.scalars(select(TenantSetting).where(TenantSetting.key == "smartcheck_connection")).all()
        for existing in rows:
            if existing.tenant_id == tenant_id:
                continue
            try:
                existing_config = json.loads(existing.value_json or "{}")
            except (TypeError, ValueError):
                continue
            if str(existing_config.get("legacy_tenant_code", "")).strip().casefold() == legacy_code.casefold():
                raise HTTPException(409, "This SmartCheck tenant code is already mapped to another AI Growth OS tenant")
    health = check_script_health(script_url)
    config = {
        "script_url": script_url,
        "drive_folder_url": drive_url,
        "legacy_tenant_code": legacy_code,
        "script_status": health["status"],
        "last_checked_by": user.id,
        "last_checked_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    row = connection_setting(db, tenant_id)
    if row:
        row.value_json = json.dumps(config)
    else:
        db.add(TenantSetting(tenant_id=tenant_id, key="smartcheck_connection", value_json=json.dumps(config)))
    db.commit()
    return {
        "tenant_id": tenant_id,
        "legacy_tenant_code": legacy_code or "",
        "script_status": health["status"],
        "script_detail": health["detail"],
        "drive_status": "link_saved_unverified" if drive_url else "not_configured",
        "authenticated_sync_ready": False,
        "note": "Authenticated bridge sync and Drive authorization have not been verified.",
    }


@router.post("/{tenant_id}/smartcheck-lifecycle/verify")
def verify_smartcheck_lifecycle(tenant_id: str, user: User = Depends(platform_user), db: Session = Depends(db_session)):
    """Enable visitor sync only after the deployed Apps Script proves each required action."""
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    row = connection_setting(db, tenant_id)
    try:
        config = json.loads(row.value_json) if row else {}
    except (TypeError, ValueError):
        config = {}
    if not config.get("script_url") or not config.get("legacy_tenant_code"):
        raise HTTPException(409, "Save the Apps Script URL and legacy tenant code first")
    if not row:
        raise HTTPException(409, "Save the SmartCheck connection before running lifecycle verification")
    config["visitor_lifecycle_sync_ready"] = False
    row.value_json = json.dumps(config)
    db.commit()
    try:
        ping = call_smartcheck(config, user, "PING")
        listed = call_smartcheck(config, user, "LIST_VISITORS")
        probe = call_smartcheck(config, user, "VERIFY_TOKEN", token="AI_GROWTH_OS_INVALID_PROBE_" + secrets.token_urlsafe(16))
        if ping.get("status") != "ok" or not isinstance(listed.get("visitors"), list) or probe.get("valid") is not False:
            raise HTTPException(409, "SmartCheck did not confirm PING, LIST_VISITORS, and VERIFY_TOKEN support")
    except HTTPException as exc:
        config["visitor_lifecycle_sync_ready"] = False
        config["lifecycle_verification_error"] = str(exc.detail)[:240]
        row.value_json = json.dumps(config)
        db.commit()
        raise
    config["visitor_lifecycle_sync_ready"] = True
    config["lifecycle_verification_error"] = ""
    config["lifecycle_verified_by"] = user.id
    config["lifecycle_verified_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    row.value_json = json.dumps(config)
    db.commit()
    return {
        "tenant_id": tenant_id,
        "visitor_lifecycle_sync_ready": True,
        "lifecycle_status": "verified",
        "checks": {"ping": "passed", "list_visitors": "passed", "verify_token": "passed"},
        "note": "Visitor lifecycle bridge verified. Google Drive folder authorization remains a separate, unverified capability.",
    }
