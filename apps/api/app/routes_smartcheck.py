"""Platform-managed SmartCheck connection diagnostics.

A successful HEALTH response proves only that the Apps Script deployment is reachable.
It does not prove bridge authentication, tenant mapping, or Drive access.
"""
from __future__ import annotations

import json
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

router = APIRouter(prefix="/api/v1/platform/tenants", tags=["smartcheck-connections"])
PLATFORM_ROLES = {"platform_admin", "super_admin"}


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
    if not user or not user.is_active or str(user.role).lower() not in PLATFORM_ROLES:
        raise HTTPException(403, "Platform administrator permission required")
    return user


class SmartCheckConnectionInput(BaseModel):
    script_url: str = Field(min_length=1, max_length=1000)
    drive_folder_url: str | None = Field(default=None, max_length=1000)


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
        "script_status": config.get("script_status", "not_configured"),
        "drive_status": "link_saved_unverified" if config.get("drive_folder_url") else "not_configured",
        "authenticated_sync_ready": False,
        "note": "Health reachability is not proof of bridge authentication or Drive access.",
    }


@router.post("/{tenant_id}/smartcheck-connection")
def save_smartcheck_connection(tenant_id: str, body: SmartCheckConnectionInput, user: User = Depends(platform_user), db: Session = Depends(db_session)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    script_url = validate_script_url(body.script_url)
    drive_url = validate_drive_url(body.drive_folder_url)
    health = check_script_health(script_url)
    config = {
        "script_url": script_url,
        "drive_folder_url": drive_url,
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
        "script_status": health["status"],
        "script_detail": health["detail"],
        "drive_status": "link_saved_unverified" if drive_url else "not_configured",
        "authenticated_sync_ready": False,
        "note": "Authenticated bridge sync and Drive authorization have not been verified.",
    }
