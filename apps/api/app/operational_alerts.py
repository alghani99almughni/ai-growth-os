"""Persistent tenant-scoped operational alerts for bookings, orders and support.
Alerts are committed alongside the event source when possible and exposed only to
users belonging to the owning tenant. Delivery is an in-app inbox, not a claim of
email/SMS/push delivery.
"""
from datetime import datetime
from uuid import uuid4
import json
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import String, Text, DateTime, Boolean, select, or_
from sqlalchemy.orm import Session, Mapped, mapped_column
from .db import Base, SessionLocal
from .config import settings
from .models import User
from .models_ai import StaffMember, Department

router = APIRouter(prefix="/api/v1/operational-alerts", tags=["operational-alerts"])

class OperationalAlert(Base):
    __tablename__ = "operational_alerts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    recipient_user_id: Mapped[str] = mapped_column(String(36), index=True)
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

def _alert_recipients(db: Session, tenant_id: str, staff_id: str | None = None, department_id: str | None = None):
    recipients = set()
    admins = db.scalars(select(User).where(User.tenant_id == tenant_id, User.is_active == True,
        User.role.in_(("owner", "tenant_admin", "admin")))).all()
    recipients.update(u.id for u in admins)
    if staff_id:
        staff = db.scalar(select(StaffMember).where(StaffMember.id == staff_id, StaffMember.tenant_id == tenant_id, StaffMember.is_active == True))
        if staff and staff.user_id:
            recipients.add(staff.user_id)
    if department_id:
        staff_rows = db.scalars(select(StaffMember).where(StaffMember.tenant_id == tenant_id,
            StaffMember.department_id == department_id, StaffMember.is_active == True)).all()
        recipients.update(s.user_id for s in staff_rows if s.user_id)
    if not recipients:
        # Safe fallback: tenant's active users only; never fan out across tenants.
        users = db.scalars(select(User).where(User.tenant_id == tenant_id, User.is_active == True)).all()
        recipients.update(u.id for u in users)
    return recipients

def create_operational_alerts(db: Session, tenant_id: str, event_type: str, title: str, message: str,
                              payload: dict | None = None, staff_id: str | None = None,
                              department_id: str | None = None):
    """Persist one alert per eligible same-tenant recipient. Caller owns commit."""
    if not tenant_id or not event_type or not title:
        return 0
    now = datetime.utcnow()
    encoded = json.dumps(payload or {}, default=str, separators=(",", ":"))
    rows = [OperationalAlert(tenant_id=tenant_id, recipient_user_id=user_id, event_type=event_type,
             title=title[:200], message=message[:4000], payload_json=encoded, created_at=now)
            for user_id in _alert_recipients(db, tenant_id, staff_id, department_id)]
    if rows:
        db.add_all(rows)
        db.flush()
    return len(rows)

def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _actor(authorization: str | None, db: Session):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Authentication required")
    try:
        claims = jwt.decode(authorization.split(" ", 1)[1], settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except Exception:
        raise HTTPException(401, "Invalid access token")
    user = db.get(User, claims.get("sub"))
    if not user or not user.is_active or not user.tenant_id:
        raise HTTPException(401, "Active tenant user required")
    return user

class ReadInput(BaseModel):
    read: bool = True

def _out(row):
    try:
        payload = json.loads(row.payload_json or "{}")
    except Exception:
        payload = {}
    return {"id": row.id, "event_type": row.event_type, "title": row.title, "message": row.message,
            "payload": payload, "read": row.read_at is not None,
            "read_at": row.read_at.isoformat() if row.read_at else None,
            "created_at": row.created_at.isoformat() + "Z"}

@router.get("")
def list_operational_alerts(unread_only: bool = False, limit: int = Query(default=100, ge=1, le=500),
                            authorization: str | None = Header(default=None), db: Session = Depends(_db)):
    user = _actor(authorization, db)
    q = select(OperationalAlert).where(OperationalAlert.tenant_id == user.tenant_id,
        OperationalAlert.recipient_user_id == user.id)
    if unread_only:
        q = q.where(OperationalAlert.read_at.is_(None))
    rows = db.scalars(q.order_by(OperationalAlert.created_at.desc()).limit(limit)).all()
    return {"items": [_out(row) for row in rows], "unread_count": db.scalar(
        select(__import__("sqlalchemy").func.count(OperationalAlert.id)).where(
            OperationalAlert.tenant_id == user.tenant_id,
            OperationalAlert.recipient_user_id == user.id,
            OperationalAlert.read_at.is_(None))) or 0}

@router.patch("/{alert_id}/read")
def mark_operational_alert_read(alert_id: str, payload: ReadInput,
                                authorization: str | None = Header(default=None), db: Session = Depends(_db)):
    user = _actor(authorization, db)
    row = db.scalar(select(OperationalAlert).where(OperationalAlert.id == alert_id,
        OperationalAlert.tenant_id == user.tenant_id, OperationalAlert.recipient_user_id == user.id))
    if not row:
        raise HTTPException(404, "Alert not found")
    row.read_at = datetime.utcnow() if payload.read else None
    db.commit()
    return _out(row)
