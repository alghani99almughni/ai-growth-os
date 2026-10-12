"""Tenant-isolated Security & Visitor Management API.

Access is always authorized against the token tenant claim and current user record.
A platform administrator may operate a selected tenant workspace, but all database
queries remain explicitly scoped to that tenant. AI/chat integrations must call the
request endpoint only; approval and gate transitions require a human role.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    tenant = db.get(Tenant, tenant_id)
    if not tenant or str(tenant.status).lower() not in ("active", "trial", "pending"):
        raise HTTPException(404, "Tenant not found or inactive")
    if user.tenant_id != tenant_id and str(user.role).lower() not in PLATFORM_ROLES:
        raise HTTPException(403, "Tenant access denied")
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
    return _create_pass(tenant_id, body, user, db, needs_approval=body.needs_approval)


@router.post("/requests")
def create_ai_request(tenant_id: str, body: VisitorRequestInput, user: User = Depends(principal), db: Session = Depends(db_session)):
    """Create a pending visitor request for AI chat/voice workflows. Never grants access."""
    tenant_access(tenant_id, user, db)
    return _create_pass(tenant_id, body, user, db, needs_approval=True)


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
