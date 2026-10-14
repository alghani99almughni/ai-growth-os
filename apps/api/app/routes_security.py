"""Tenant-isolated Security & Visitor Management API.

Access is always authorized against the token tenant claim and current user record.
A platform administrator may operate a selected tenant workspace, but all database
queries remain explicitly scoped to that tenant. AI/chat integrations must call the
request endpoint only; approval and gate transitions require a human role.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import secrets
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
import qrcode

from .config import settings
from .db import SessionLocal
from .models import Tenant, User
from .models_growth import TenantSetting, PlatformSetting
from .models_security import SecuritySite, VisitorPass, VisitorEvent
from .security import decode_token_strict

router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/security", tags=["security-visitor-management"])
ADMIN_ROLES = {"owner", "admin", "tenant_admin", "manager", "security_admin", "platform_admin", "super_admin"}
PLATFORM_ROLES = {"platform_admin", "super_admin"}


def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def principal(authorization: str | None = Header(default=None), db: Session = Depends(db_session)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer token required")
    try:
        payload = decode_token_strict(authorization.split(" ", 1)[1], settings.jwt_secret, settings.jwt_algorithm)
    except (ValueError, jwt.InvalidTokenError):
        raise HTTPException(401, "Invalid access token")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active or payload.get("tenant_id") != user.tenant_id:
        raise HTTPException(401, "Invalid tenant context")
    tenant = db.get(Tenant, user.tenant_id)
    if not tenant or str(tenant.status).lower() != "active":
        raise HTTPException(403, "Tenant is not active")
    return user


def tenant_access(tenant_id: str, user: User, db: Session, *, require_feature: bool = True):
    # Reject cross-tenant users before looking up the requested tenant to avoid
    # exposing whether another tenant identifier exists.
    if user.tenant_id != tenant_id and str(user.role).lower() not in PLATFORM_ROLES:
        raise HTTPException(403, "Tenant access denied")
    tenant = db.get(Tenant, tenant_id)
    if not tenant or str(tenant.status).lower() not in ("active", "trial", "pending"):
        raise HTTPException(404, "Tenant not found or inactive")
    if require_feature:
        row = db.scalar(select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id, TenantSetting.key == "features"
        ))
        defaults_row = db.scalar(select(PlatformSetting).where(PlatformSetting.key == "feature_defaults"))
        try:
            features = json.loads(row.value_json) if row else {}
        except (TypeError, ValueError):
            features = {}
        try:
            defaults = json.loads(defaults_row.value_json) if defaults_row else {}
        except (TypeError, ValueError):
            defaults = {}
        # Tenant overrides take precedence; platform default is opt-in and false when absent.
        enabled = features.get("security_visitor_management", defaults.get("security_visitor_management", False))
        if not enabled:
            raise HTTPException(403, "Security & Visitor Management is disabled for this tenant")


def admin_only(user: User):
    if str(user.role).lower() not in ADMIN_ROLES:
        raise HTTPException(403, "Administrator permission required")


def gate_staff(user: User):
    if str(user.role).lower() not in ADMIN_ROLES and str(user.role).lower() not in {"reception", "security", "guard", "security_guard"}:
        raise HTTPException(403, "Security or administrator role required")


class SiteInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    industry: str = Field(default="apartment", pattern="^(school|apartment|hospital)$")


class PassInput(BaseModel):
    visitor_name: str = Field(min_length=1, max_length=160)
    visitor_mobile: str = Field(default="", max_length=32)
    purpose: str = Field(default="", max_length=240)
    destination: str = Field(default="", max_length=240)
    vehicle_number: str = Field(default="", max_length=40)
    industry: str = Field(default="apartment", pattern="^(school|apartment|hospital)$")
    site_id: str | None = None
    needs_approval: bool = True
    valid_hours: int = Field(default=24, ge=1, le=168)


class VisitorRequestInput(BaseModel):
    """Safe request payload for AI chat/voice; it cannot approve or admit anyone."""
    visitor_name: str = Field(min_length=1, max_length=160)
    visitor_mobile: str = Field(default="", max_length=32)
    purpose: str = Field(default="", max_length=240)
    destination: str = Field(default="", max_length=240)
    vehicle_number: str = Field(default="", max_length=40)
    site_id: str | None = None


class VerifyTokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=256)


def event(db: Session, tenant_id: str, pass_id: str, actor_id: str, kind: str, details: dict[str, Any] | None = None):
    db.add(VisitorEvent(tenant_id=tenant_id, pass_id=pass_id, actor_id=actor_id,
                        event_type=kind, details_json=json.dumps(details or {}, separators=(",", ":"))))


def pass_json(p: VisitorPass, token: str | None = None):
    return {
        "id": p.id, "tenant_id": p.tenant_id, "site_id": p.site_id,
        "visitor_name": p.visitor_name, "visitor_mobile": p.visitor_mobile,
        "purpose": p.purpose, "destination": p.destination, "vehicle_number": p.vehicle_number,
        "industry": p.industry, "status": p.status,
        "expires_at": p.expires_at.isoformat() if p.expires_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "checked_in_at": p.checked_in_at.isoformat() if p.checked_in_at else None,
        "checked_out_at": p.checked_out_at.isoformat() if p.checked_out_at else None,
        "qr_token": token,
    }


def _site_for_tenant(db: Session, tenant_id: str, site_id: str | None):
    if not site_id:
        return None
    site = db.scalar(select(SecuritySite).where(SecuritySite.id == site_id, SecuritySite.tenant_id == tenant_id, SecuritySite.enabled.is_(True)))
    if not site:
        raise HTTPException(404, "Enabled site not found")
    return site


def _create_pass(tenant_id: str, body: VisitorRequestInput | PassInput, user: User, db: Session, needs_approval: bool = True):
    site = _site_for_tenant(db, tenant_id, body.site_id)
    industry = site.industry if site else getattr(body, "industry", "apartment")
    raw = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    p = VisitorPass(
        tenant_id=tenant_id, site_id=site.id if site else None,
        token_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        visitor_name=body.visitor_name.strip(), visitor_mobile=body.visitor_mobile.strip(),
        purpose=body.purpose.strip(), destination=body.destination.strip(),
        vehicle_number=body.vehicle_number.strip().upper(), industry=industry,
        status="pending" if needs_approval else "approved",
        expires_at=now + timedelta(hours=getattr(body, "valid_hours", 24)),
        created_by=user.id, approved_by=None,
    )
    db.add(p)
    db.flush()
    event(db, tenant_id, p.id, user.id, "visitor_request_created" if isinstance(body, VisitorRequestInput) else "pass_created",
          {"status": p.status, "source": "ai_or_chat" if isinstance(body, VisitorRequestInput) else "dashboard"})
    db.commit()
    db.refresh(p)
    return pass_json(p, raw)


@router.get("/sites")
def list_sites(tenant_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id, user, db)
    rows = db.scalars(select(SecuritySite).where(SecuritySite.tenant_id == tenant_id).order_by(SecuritySite.created_at.desc())).all()
    return {"items": [{"id": s.id, "name": s.name, "industry": s.industry, "enabled": s.enabled,
                       "settings": json.loads(s.settings_json or "{}")} for s in rows]}


@router.post("/sites")
def create_site(tenant_id: str, body: SiteInput, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id, user, db)
    admin_only(user)
    s = SecuritySite(tenant_id=tenant_id, name=body.name.strip(), industry=body.industry)
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"id": s.id, "name": s.name, "industry": s.industry, "enabled": s.enabled}


@router.get("/passes")
def list_passes(tenant_id: str, user: User = Depends(principal), db: Session = Depends(db_session), status: str | None = None, limit: int = 100):
    tenant_access(tenant_id, user, db)
    q = select(VisitorPass).where(VisitorPass.tenant_id == tenant_id).order_by(VisitorPass.created_at.desc()).limit(max(1, min(limit, 200)))
    if status:
        q = q.where(VisitorPass.status == status)
    return {"items": [pass_json(p) for p in db.scalars(q).all()]}


@router.post("/passes")
def create_pass(tenant_id: str, body: PassInput, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id, user, db)
    admin_only(user)
    # Never allow a request payload to bypass human approval. Every new pass
    # starts pending; the separate approve endpoint records the approving actor.
    if not body.needs_approval:
        raise HTTPException(422, "New visitor passes must require human approval")
    return _create_pass(tenant_id, body, user, db, needs_approval=True)


@router.post("/requests")
def create_ai_request(tenant_id: str, body: VisitorRequestInput, user: User = Depends(principal), db: Session = Depends(db_session)):
    """Create a pending visitor request for AI chat/voice workflows. Never grants access."""
    tenant_access(tenant_id, user, db)
    return _create_pass(tenant_id, body, user, db, needs_approval=True)


@router.post("/qr")
def render_qr(tenant_id: str, body: VerifyTokenInput, user: User = Depends(principal), db: Session = Depends(db_session)):
    """Render a QR image only for a token belonging to an unexpired pass in this tenant."""
    tenant_access(tenant_id, user, db)
    digest = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    p = db.scalar(select(VisitorPass).where(VisitorPass.tenant_id == tenant_id, VisitorPass.token_hash == digest))
    if not p:
        raise HTTPException(404, "Visitor token not found for this tenant")
    if p.status not in {"pending", "approved"} or (p.expires_at and p.expires_at <= datetime.utcnow()):
        raise HTTPException(409, "QR can only be rendered for a current visitor pass")
    image = qrcode.make(body.token)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return {"image_data_url": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii"),
            "pass_id": p.id, "status": p.status}


@router.post("/verify-token")
def verify_token(tenant_id: str, body: VerifyTokenInput, user: User = Depends(principal), db: Session = Depends(db_session)):
    """Validate a QR/token for the selected tenant; verification does not admit the visitor."""
    tenant_access(tenant_id, user, db)
    digest = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    p = db.scalar(select(VisitorPass).where(VisitorPass.tenant_id == tenant_id, VisitorPass.token_hash == digest))
    if not p:
        raise HTTPException(404, "Invalid visitor token")
    if p.expires_at and p.expires_at <= datetime.utcnow():
        if p.status in {"pending", "approved"}:
            p.status = "expired"
            event(db, tenant_id, p.id, user.id, "pass_expired")
            db.commit()
        raise HTTPException(410, "Visitor pass expired")
    if p.status != "approved":
        raise HTTPException(409, "Pass is not approved or has already been used")
    event(db, tenant_id, p.id, user.id, "pass_token_verified", {"status": p.status})
    db.commit()
    return {"valid": True, "pass": pass_json(p)}


@router.post("/passes/{pass_id}/approve")
def approve_pass(tenant_id: str, pass_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id, user, db)
    admin_only(user)
    p = db.scalar(select(VisitorPass).where(VisitorPass.id == pass_id, VisitorPass.tenant_id == tenant_id))
    if not p:
        raise HTTPException(404, "Pass not found")
    if p.status != "pending":
        raise HTTPException(409, "Only pending passes can be approved")
    if p.expires_at and p.expires_at <= datetime.utcnow():
        p.status = "expired"
        event(db, tenant_id, p.id, user.id, "approval_rejected_expired")
        db.commit()
        raise HTTPException(410, "Pass expired")
    p.status = "approved"
    p.approved_by = user.id
    event(db, tenant_id, p.id, user.id, "pass_approved")
    db.commit()
    db.refresh(p)
    return pass_json(p)


@router.post("/passes/{pass_id}/check-in")
def check_in(tenant_id: str, pass_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id, user, db)
    gate_staff(user)
    p = db.scalar(select(VisitorPass).where(VisitorPass.id == pass_id, VisitorPass.tenant_id == tenant_id))
    if not p:
        raise HTTPException(404, "Pass not found")
    if p.status != "approved":
        raise HTTPException(409, "Pass must be approved and unused before entry")
    if p.expires_at and p.expires_at <= datetime.utcnow():
        p.status = "expired"
        event(db, tenant_id, p.id, user.id, "check_in_rejected_expired")
        db.commit()
        raise HTTPException(410, "Pass expired")
    p.status = "checked_in"
    p.checked_in_at = datetime.utcnow()
    event(db, tenant_id, p.id, user.id, "visitor_checked_in")
    db.commit()
    db.refresh(p)
    return pass_json(p)


@router.post("/passes/{pass_id}/check-out")
def check_out(tenant_id: str, pass_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    tenant_access(tenant_id, user, db)
    gate_staff(user)
    p = db.scalar(select(VisitorPass).where(VisitorPass.id == pass_id, VisitorPass.tenant_id == tenant_id))
    if not p:
        raise HTTPException(404, "Pass not found")
    if p.status != "checked_in":
        raise HTTPException(409, "Only checked-in visitors can check out")
    p.status = "checked_out"
    p.checked_out_at = datetime.utcnow()
    event(db, tenant_id, p.id, user.id, "visitor_checked_out")
    db.commit()
    db.refresh(p)
    return pass_json(p)


@router.get("/events")
def list_events(tenant_id: str, user: User = Depends(principal), db: Session = Depends(db_session), limit: int = 200):
    tenant_access(tenant_id, user, db)
    rows = db.scalars(select(VisitorEvent).where(VisitorEvent.tenant_id == tenant_id).order_by(VisitorEvent.created_at.desc()).limit(max(1, min(limit, 500)))).all()
    return {"items": [{"id": e.id, "pass_id": e.pass_id, "event_type": e.event_type, "actor_id": e.actor_id,
                       "details": json.loads(e.details_json or "{}"), "created_at": e.created_at.isoformat()} for e in rows]}

@router.post("/passes/{pass_id}/deny")
def deny_pass(tenant_id: str, pass_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    """Record an explicit human denial; a denied pass can never be admitted."""
    tenant_access(tenant_id, user, db)
    admin_only(user)
    p = db.scalar(select(VisitorPass).where(
        VisitorPass.id == pass_id, VisitorPass.tenant_id == tenant_id
    ))
    if not p:
        raise HTTPException(404, "Pass not found")
    if p.status != "pending":
        raise HTTPException(409, "Only pending passes can be denied")
    p.status = "denied"
    event(db, tenant_id, p.id, user.id, "pass_denied")
    db.commit()
    db.refresh(p)
    return pass_json(p)


@router.post("/passes/{pass_id}/cancel")
def cancel_pass(tenant_id: str, pass_id: str, user: User = Depends(principal), db: Session = Depends(db_session)):
    """Cancel a pending or approved pass without altering completed gate history."""
    tenant_access(tenant_id, user, db)
    admin_only(user)
    p = db.scalar(select(VisitorPass).where(
        VisitorPass.id == pass_id, VisitorPass.tenant_id == tenant_id
    ))
    if not p:
        raise HTTPException(404, "Pass not found")
    if p.status not in {"pending", "approved"}:
        raise HTTPException(409, "Only pending or approved passes can be cancelled")
    p.status = "cancelled"
    event(db, tenant_id, p.id, user.id, "pass_cancelled")
    db.commit()
    db.refresh(p)
    return pass_json(p)



# ======================================================================
# SMARTCHECK / SNAPSHEET GOOGLE SHEETS + DRIVE COMPATIBILITY
# ======================================================================

class SmartCheckConfigInput(BaseModel):
    web_app_url: str = Field(min_length=1, max_length=2048)
    shared_secret: str = Field(min_length=24, max_length=256)
    enabled: bool = True


class SmartCheckLegacyTicket(BaseModel):
    ticket_id: str = Field(min_length=1, max_length=160)
    tenant_id: str | None = Field(default=None, max_length=160)
    visitor_name: str = Field(min_length=1, max_length=160)
    visitor_mobile: str = Field(default="", max_length=32)
    purpose: str = Field(default="", max_length=240)
    target_destination: str = Field(default="", max_length=240)
    vehicle_number: str = Field(default="", max_length=40)
    industry: str = Field(default="apartment", pattern="^(school|apartment|hospital)$")
    site_id: str | None = None
    status: str = Field(default="PENDING_APPROVAL", max_length=40)


class SmartCheckMigrationInput(BaseModel):
    tickets: list[SmartCheckLegacyTicket] = Field(min_length=1, max_length=500)


SMARTCHECK_CONFIG_KEY = "smartcheck_google_apps_script"


def _smartcheck_fernet_key() -> bytes:
    import base64
    return base64.urlsafe_b64encode(hashlib.sha256(
        (settings.jwt_secret + ":smartcheck-config:v1").encode("utf-8")
    ).digest())


def _encrypt_smartcheck_secret(secret: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_smartcheck_fernet_key()).encrypt(secret.encode("utf-8")).decode("ascii")


def _decrypt_smartcheck_secret(value: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(_smartcheck_fernet_key()).decrypt(value.encode("ascii")).decode("utf-8")


def _validate_smartcheck_url(value: str) -> str:
    from urllib.parse import urlsplit
    parsed = urlsplit((value or "").strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "script.google.com"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/macros/s/")
        or not parsed.path.endswith("/exec")
    ):
        raise HTTPException(
            422,
            "Use the HTTPS Google Apps Script deployment URL ending in /macros/s/{deployment-id}/exec",
        )
    return value.strip()


def _smartcheck_config(db: Session, tenant_id: str) -> dict:
    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == SMARTCHECK_CONFIG_KEY,
    ))
    if not row:
        return {"enabled": False, "web_app_url": ""}
    try:
        value = json.loads(row.value_json or "{}")
    except (TypeError, ValueError):
        value = {}
    encrypted_secret = str(value.get("shared_secret_encrypted") or "")
    try:
        shared_secret = _decrypt_smartcheck_secret(encrypted_secret) if encrypted_secret else ""
    except Exception:
        shared_secret = ""
    return {
        "enabled": bool(value.get("enabled")),
        "web_app_url": str(value.get("web_app_url") or ""),
        "shared_secret": shared_secret,
    }


def _require_smartcheck_config(db: Session, tenant_id: str) -> dict:
    config = _smartcheck_config(db, tenant_id)
    if not config["enabled"] or not config["web_app_url"]:
        raise HTTPException(409, "SmartCheck Google Sheets sync is not configured for this tenant")
    _validate_smartcheck_url(config["web_app_url"])
    return config


@router.get("/smartcheck/config")
def get_smartcheck_config(
    tenant_id: str,
    user: User = Depends(principal),
    db: Session = Depends(db_session),
):
    tenant_access(tenant_id, user, db, require_feature=False)
    admin_only(user)
    config = _smartcheck_config(db, tenant_id)
    return {
        "enabled": config["enabled"],
        "web_app_url": config["web_app_url"],
        "has_shared_secret": bool(config["shared_secret"]),
    }


@router.put("/smartcheck/config")
def save_smartcheck_config(
    tenant_id: str,
    payload: SmartCheckConfigInput,
    user: User = Depends(principal),
    db: Session = Depends(db_session),
):
    tenant_access(tenant_id, user, db, require_feature=False)
    admin_only(user)
    url = _validate_smartcheck_url(payload.web_app_url)
    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == SMARTCHECK_CONFIG_KEY,
    ))
    value = json.dumps({
        "enabled": payload.enabled,
        "web_app_url": url,
        "shared_secret_encrypted": _encrypt_smartcheck_secret(payload.shared_secret),
    })
    if row:
        row.value_json = value
    else:
        db.add(TenantSetting(
            id=str(uuid.uuid4()), tenant_id=tenant_id,
            key=SMARTCHECK_CONFIG_KEY, value_json=value,
        ))
    db.commit()
    return {"saved": True, "enabled": payload.enabled, "web_app_url": url}


@router.post("/smartcheck/ping")
async def ping_smartcheck(
    tenant_id: str,
    user: User = Depends(principal),
    db: Session = Depends(db_session),
):
    tenant_access(tenant_id, user, db)
    admin_only(user)
    config = _require_smartcheck_config(db, tenant_id)
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.post(
                config["web_app_url"],
                json={
                    "action": "PING", "tenantId": tenant_id, "type": "TEST_PING",
                    "apiKey": config["shared_secret"],
                },
            )
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError:
            raise HTTPException(502, "Google Apps Script returned a non-JSON response")
        if str(body.get("status", "")).lower() in {"error", "failed"}:
            raise HTTPException(502, "Google Apps Script ping failed")
        return {"connected": True, "response": body}
    except HTTPException:
        raise
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach the configured Google Apps Script deployment")


@router.post("/passes/{pass_id}/smartcheck-sync")
async def sync_pass_to_smartcheck(
    tenant_id: str,
    pass_id: str,
    user: User = Depends(principal),
    db: Session = Depends(db_session),
):
    """Mirror one pass to the tenant's legacy sheet; AI Growth OS remains authoritative."""
    tenant_access(tenant_id, user, db)
    admin_only(user)
    config = _require_smartcheck_config(db, tenant_id)
    p = db.scalar(select(VisitorPass).where(
        VisitorPass.id == pass_id, VisitorPass.tenant_id == tenant_id
    ))
    if not p:
        raise HTTPException(404, "Visitor pass not found")
    status_map = {
        "pending": "PENDING_APPROVAL", "approved": "APPROVED",
        "denied": "REJECTED", "checked_in": "CHECKED_IN",
        "checked_out": "CHECKED_OUT", "cancelled": "CANCELLED",
        "expired": "EXPIRED",
    }
    payload = {
        "action": "SYNC_TICKET",
        "tenantId": tenant_id,
        "apiKey": config["shared_secret"],
        "ticketId": p.id,
        "visitorName": p.visitor_name,
        "visitorMobile": p.visitor_mobile or "",
        "purpose": p.purpose or "",
        "targetDestination": p.destination or "",
        "vehicleNumber": p.vehicle_number or "",
        "vehicleSnapshotUri": p.snapshot_url or "",
        "status": status_map.get(p.status, "PENDING_APPROVAL"),
        # Raw QR tokens are intentionally not stored in AI Growth OS and are never exported.
        "qrToken": "",
        "approverName": p.approved_by or "",
        "gateEntryTime": p.checked_in_at.isoformat() if p.checked_in_at else "",
        "gateExitTime": p.checked_out_at.isoformat() if p.checked_out_at else "",
        "updatedAt": p.created_at.isoformat() if p.created_at else "",
    }
    import httpx
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.post(config["web_app_url"], json=payload)
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError:
            raise HTTPException(502, "Google Apps Script returned a non-JSON response")
        if str(body.get("status", "")).lower() in {"error", "failed"}:
            raise HTTPException(502, "Google Apps Script rejected the visitor log")
    except HTTPException:
        raise
    except httpx.HTTPError:
        raise HTTPException(502, "Could not sync visitor pass to Google Apps Script")
    event(db, tenant_id, p.id, user.id, "smartcheck_sheet_sync", {"remote_status": body.get("status", "unknown")})
    db.commit()
    return {"synced": True, "pass_id": p.id, "remote_status": body.get("status", "unknown")}


@router.post("/smartcheck/migrate-pending")
def migrate_smartcheck_pending(
    tenant_id: str,
    payload: SmartCheckMigrationInput,
    user: User = Depends(principal),
    db: Session = Depends(db_session),
):
    """Import pending rows exported from a legacy Google Sheet.

    Imports are idempotent. Existing approved/closed legacy rows are not auto-approved;
    they are reported for archival/manual reconciliation rather than bypassing review.
    """
    tenant_access(tenant_id, user, db)
    admin_only(user)
    imported = 0
    duplicates = 0
    rejected = []
    created = []
    now = datetime.utcnow()
    for index, row in enumerate(payload.tickets, start=1):
        if row.tenant_id and row.tenant_id != tenant_id:
            rejected.append({"row": index, "ticket_id": row.ticket_id, "reason": "tenant_mismatch"})
            continue
        if row.status.strip().lower() not in {"pending", "pending_approval", "pending approval", "awaiting_approval"}:
            rejected.append({"row": index, "ticket_id": row.ticket_id, "reason": "non_pending_requires_manual_reconciliation"})
            continue
        deterministic_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"aigrowthos:smartcheck:{tenant_id}:{row.ticket_id.strip()}"))
        if db.get(VisitorPass, deterministic_id):
            duplicates += 1
            continue
        try:
            site = _site_for_tenant(db, tenant_id, row.site_id)
        except HTTPException:
            rejected.append({"row": index, "ticket_id": row.ticket_id, "reason": "invalid_site"})
            continue
        raw_token = secrets.token_urlsafe(32)
        p = VisitorPass(
            id=deterministic_id,
            tenant_id=tenant_id,
            site_id=site.id if site else None,
            token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
            visitor_name=row.visitor_name.strip(),
            visitor_mobile=row.visitor_mobile.strip(),
            purpose=row.purpose.strip(),
            destination=row.target_destination.strip(),
            vehicle_number=row.vehicle_number.strip(),
            industry=site.industry if site else row.industry,
            status="pending",
            expires_at=now + timedelta(hours=24),
            created_by=user.id,
        )
        db.add(p)
        db.flush()
        event(db, tenant_id, p.id, user.id, "smartcheck_legacy_import", {
            "source_ticket_id": row.ticket_id.strip(),
            "original_status": row.status,
            "requires_human_approval": True,
        })
        created.append({"pass_id": p.id, "source_ticket_id": row.ticket_id.strip(), "qr_token": raw_token})
        imported += 1
    db.commit()
    return {"imported": imported, "duplicates": duplicates, "rejected": rejected, "created": created}
