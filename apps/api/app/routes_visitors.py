"""Tenant-isolated visitor management API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import Tenant, User
from .models_ai import StaffMember
from .models_visitors import VisitorRecord
from .security import decode_token_strict, audit

router = APIRouter()
_bearer = HTTPBearer(auto_error=False)
VALID_STATUSES = {"pending", "approved", "checked_in", "checked_out", "denied", "cancelled"}
TRANSITIONS = {
    "pending": {"approved", "denied", "cancelled"},
    "approved": {"checked_in", "cancelled"},
    "checked_in": {"checked_out"},
    "checked_out": set(), "denied": set(), "cancelled": set(),
}


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "Authentication required")
    try:
        payload = decode_token_strict(creds.credentials, settings.jwt_secret, settings.jwt_algorithm)
    except ValueError as exc:
        raise HTTPException(401, str(exc))
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active or payload.get("tenant_id") != user.tenant_id:
        raise HTTPException(401, "Invalid tenant context")
    return user


def _check_tenant(tenant_id: str, user: User, db: Session) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if not tenant or tenant.status != "active":
        raise HTTPException(404, "Business not found")
    if user.role not in ("platform_admin", "super_admin") and user.tenant_id != tenant_id:
        raise HTTPException(403, "Cannot access another business's visitors")
    return tenant


class VisitorCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    phone: str = Field(min_length=5, max_length=32)
    email: EmailStr | None = None
    organization: str | None = Field(default=None, max_length=160)
    purpose: str = Field(min_length=2, max_length=240)
    host_name: str | None = Field(default=None, max_length=160)
    host_staff_id: str | None = None
    scheduled_for: datetime | None = None
    expected_checkout: datetime | None = None
    notes: str | None = Field(default=None, max_length=3000)
    consent_confirmed: bool = False


class VisitorStatusUpdate(BaseModel):
    status: Literal["approved", "checked_in", "checked_out", "denied", "cancelled"]
    notes: str | None = Field(default=None, max_length=3000)


def _out(row: VisitorRecord) -> dict:
    return {
        "id": row.id, "tenant_id": row.tenant_id, "full_name": row.full_name,
        "phone": row.phone, "email": row.email, "organization": row.organization,
        "purpose": row.purpose, "host_name": row.host_name, "host_staff_id": row.host_staff_id,
        "scheduled_for": row.scheduled_for.isoformat() if row.scheduled_for else None,
        "expected_checkout": row.expected_checkout.isoformat() if row.expected_checkout else None,
        "checked_in_at": row.checked_in_at.isoformat() if row.checked_in_at else None,
        "checked_out_at": row.checked_out_at.isoformat() if row.checked_out_at else None,
        "status": row.status, "pass_token": row.pass_token, "notes": row.notes,
        "consent_confirmed": row.consent_confirmed,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/api/v1/tenants/{tenant_id}/visitors")
def list_visitors(
    tenant_id: str,
    status: str | None = Query(default=None),
    q: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=100, ge=1, le=250),
    user: User = Depends(_current_user),
    db: Session = Depends(_db),
):
    _check_tenant(tenant_id, user, db)
    if status and status not in VALID_STATUSES:
        raise HTTPException(400, "Invalid visitor status")
    stmt = select(VisitorRecord).where(VisitorRecord.tenant_id == tenant_id)
    if status:
        stmt = stmt.where(VisitorRecord.status == status)
    if q:
        pattern = "%" + q.strip() + "%"
        stmt = stmt.where(or_(VisitorRecord.full_name.ilike(pattern), VisitorRecord.phone.ilike(pattern), VisitorRecord.organization.ilike(pattern), VisitorRecord.host_name.ilike(pattern)))
    rows = db.scalars(stmt.order_by(VisitorRecord.created_at.desc()).limit(limit)).all()
    return {"items": [_out(row) for row in rows], "count": len(rows)}


@router.post("/api/v1/tenants/{tenant_id}/visitors", status_code=201)
def create_visitor(
    tenant_id: str,
    payload: VisitorCreate,
    user: User = Depends(_current_user),
    db: Session = Depends(_db),
):
    _check_tenant(tenant_id, user, db)
    if payload.host_staff_id:
        staff = db.scalar(select(StaffMember).where(StaffMember.id == payload.host_staff_id, StaffMember.tenant_id == tenant_id))
        if not staff:
            raise HTTPException(400, "Host must belong to this business")
    if payload.scheduled_for and payload.expected_checkout and payload.expected_checkout < payload.scheduled_for:
        raise HTTPException(400, "Expected checkout cannot be before the scheduled visit")
    row = VisitorRecord(
        id=str(uuid.uuid4()), tenant_id=tenant_id, full_name=payload.full_name.strip(),
        phone=payload.phone.strip(), email=str(payload.email) if payload.email else None,
        organization=payload.organization.strip() if payload.organization else None,
        purpose=payload.purpose.strip(), host_name=payload.host_name.strip() if payload.host_name else None,
        host_staff_id=payload.host_staff_id, scheduled_for=payload.scheduled_for,
        expected_checkout=payload.expected_checkout, notes=payload.notes,
        consent_confirmed=payload.consent_confirmed, created_by_user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, user.id, "visitor.created", {"tenant_id": tenant_id, "visitor_id": row.id})
    return _out(row)


@router.post("/api/v1/tenants/{tenant_id}/visitors/{visitor_id}/status")
def update_visitor_status(
    tenant_id: str,
    visitor_id: str,
    payload: VisitorStatusUpdate,
    user: User = Depends(_current_user),
    db: Session = Depends(_db),
):
    _check_tenant(tenant_id, user, db)
    row = db.scalar(select(VisitorRecord).where(VisitorRecord.id == visitor_id, VisitorRecord.tenant_id == tenant_id))
    if not row:
        raise HTTPException(404, "Visitor not found")
    if payload.status not in TRANSITIONS.get(row.status, set()):
        raise HTTPException(409, f"Cannot change visitor status from {row.status} to {payload.status}")
    now = datetime.utcnow()
    row.status = payload.status
    if payload.status == "checked_in":
        row.checked_in_at = now
    elif payload.status == "checked_out":
        row.checked_out_at = now
    if payload.notes:
        row.notes = payload.notes
    row.updated_at = now
    db.commit()
    db.refresh(row)
    audit(db, user.id, "visitor.status_changed", {"tenant_id": tenant_id, "visitor_id": row.id, "status": row.status})
    return _out(row)


@router.get("/api/v1/tenants/{tenant_id}/visitors/pass/{pass_token}")
def verify_visitor_pass(
    tenant_id: str,
    pass_token: str,
    user: User = Depends(_current_user),
    db: Session = Depends(_db),
):
    _check_tenant(tenant_id, user, db)
    row = db.scalar(select(VisitorRecord).where(VisitorRecord.tenant_id == tenant_id, VisitorRecord.pass_token == pass_token))
    if not row:
        raise HTTPException(404, "Visitor pass not found")
    return {"valid": row.status in ("approved", "checked_in"), "visitor": _out(row)}
