"""Persistent tenant-scoped operational alerts for bookings, orders and support.
Alerts are committed alongside the event source when possible and exposed only to
users belonging to the owning tenant. Delivery is an in-app inbox, not a claim of
email/SMS/push delivery.
"""
from datetime import datetime, timedelta
from uuid import uuid4
import json
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import String, Text, DateTime, Boolean, select, func
from sqlalchemy.orm import Session, Mapped, mapped_column
from .db import Base, SessionLocal
from .config import settings
from .models import User
from .models_ai import StaffMember, Department

router = APIRouter(prefix="/api/v1/operational-alerts", tags=["operational-alerts"])

class TicketEscalation(Base):
    __tablename__ = "ticket_escalations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    ticket_id: Mapped[str] = mapped_column(String(36), index=True)
    from_status: Mapped[str] = mapped_column(String(40), default="new")
    to_status: Mapped[str] = mapped_column(String(40), default="in_progress")
    department_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    assigned_staff_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    room_key: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    escalated_by: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

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

def _alert_recipients(db: Session, tenant_id: str, event_type: str, staff_id: str | None = None, department_id: str | None = None):
    recipients = set()
    admins = db.scalars(select(User).where(User.tenant_id == tenant_id, User.is_active == True,
        User.role.in_(("owner", "tenant_admin", "admin")))).all()
    recipients.update(u.id for u in admins)
    if staff_id:
        staff = db.scalar(select(StaffMember).where(StaffMember.id == staff_id, StaffMember.tenant_id == tenant_id, StaffMember.is_active == True))
        if staff and staff.user_id:
            recipients.add(staff.user_id)
    target_department_ids = {department_id} if department_id else set()
    if not department_id:
        # Route unassigned booking/order alerts to operational departments as well as tenant admins.
        if event_type.startswith("appointment."):
            patterns = ("%booking%", "%reception%", "%front desk%", "%appointment%")
        elif event_type.startswith("order."):
            patterns = ("%order%", "%kitchen%", "%operations%", "%reception%")
        else:
            patterns = ()
        for pattern in patterns:
            rows = db.scalars(select(Department).where(Department.tenant_id == tenant_id,
                Department.is_active == True, Department.name.ilike(pattern))).all()
            target_department_ids.update(d.id for d in rows)
    if target_department_ids:
        staff_rows = db.scalars(select(StaffMember).where(StaffMember.tenant_id == tenant_id,
            StaffMember.department_id.in_(target_department_ids), StaffMember.is_active == True)).all()
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
            for user_id in _alert_recipients(db, tenant_id, event_type, staff_id, department_id)]
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

class TicketDepartmentCorrection(BaseModel):
    department_id: str | None = None
    reason: str = "Department routing corrected by tenant administrator"

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
        select(func.count(OperationalAlert.id)).where(
            OperationalAlert.tenant_id == user.tenant_id,
            OperationalAlert.recipient_user_id == user.id,
            OperationalAlert.read_at.is_(None))) or 0}

@router.get("/tickets/{ticket_id}/escalations")
def list_ticket_escalations(ticket_id: str, authorization: str | None = Header(default=None), db: Session = Depends(_db)):
    user = _actor(authorization, db)
    from .models_growth import SupportTicket
    ticket = db.scalar(select(SupportTicket).where(SupportTicket.id == ticket_id, SupportTicket.tenant_id == user.tenant_id))
    if not ticket:
        raise HTTPException(404, "Ticket not found")
    rows = db.scalars(select(TicketEscalation).where(TicketEscalation.tenant_id == user.tenant_id,
        TicketEscalation.ticket_id == ticket_id).order_by(TicketEscalation.created_at.asc())).all()
    return {"items": [{"id":r.id,"ticket_id":r.ticket_id,"from_status":r.from_status,"to_status":r.to_status,
        "department_id":r.department_id,"assigned_staff_id":r.assigned_staff_id,"room_key":r.room_key,"reason":r.reason,
        "escalated_by":r.escalated_by,"created_at":r.created_at.isoformat()+"Z"} for r in rows]}

@router.patch("/tickets/{ticket_id}/department")
def correct_ticket_department(ticket_id: str, payload: TicketDepartmentCorrection,
                              authorization: str | None = Header(default=None), db: Session = Depends(_db)):
    """Allow tenant admins to correct an escalated ticket's department without resetting its age or original SLA."""
    user = _actor(authorization, db)
    if user.role not in {"owner", "tenant_admin", "admin"}:
        raise HTTPException(403, "Tenant administrator permission required")

    from .models_growth import SupportTicket
    from .ticket_escalation_automation import TicketAutoEscalationClaim
    from .routes_team_comms import TeamMessage

    ticket = db.scalar(select(SupportTicket).where(
        SupportTicket.id == ticket_id, SupportTicket.tenant_id == user.tenant_id
    ))
    if not ticket:
        raise HTTPException(404, "Ticket not found")

    claim = db.scalar(select(TicketAutoEscalationClaim).where(
        TicketAutoEscalationClaim.ticket_id == ticket.id,
        TicketAutoEscalationClaim.tenant_id == user.tenant_id
    ))
    if not claim:
        raise HTTPException(409, "Ticket has not been automatically escalated")

    department = None
    if payload.department_id:
        department = db.scalar(select(Department).where(
            Department.id == payload.department_id,
            Department.tenant_id == user.tenant_id,
            Department.is_active.is_(True)
        ))
        if not department:
            raise HTTPException(404, "Active department not found in this workspace")

    previous_department_id = claim.department_id
    claim.department_id = department.id if department else None
    response_hours = max(1, int(ticket.sla_hours or 24))
    claim.department_response_due_at = datetime.utcnow() + timedelta(hours=response_hours)

    latest_event = db.scalar(select(TicketEscalation).where(
        TicketEscalation.ticket_id == ticket.id,
        TicketEscalation.tenant_id == user.tenant_id
    ).order_by(TicketEscalation.created_at.desc()))
    if latest_event:
        latest_event.department_id = claim.department_id
        latest_event.reason = (latest_event.reason or "") + " | Routing correction: " + payload.reason[:500]

    now = datetime.utcnow()
    destination = department.name if department else "Escalation"
    db.add(TeamMessage(
        tenant_id=user.tenant_id, sender_id=user.id, sender_name=user.name,
        recipient_id=None, room="escalation",
        message=f"[ROUTING CORRECTION · Ticket #{ticket.id}] {ticket.subject}\\n"
                f"Department: {destination}\\nReason: {payload.reason[:500]}",
        formatting="bold", attachment_id=None, created_at=now
    ))
    create_operational_alerts(
        db, user.tenant_id, "ticket.department_corrected", "Ticket department corrected",
        f"{ticket.subject} routed to {destination}",
        {"ticket_id": ticket.id, "previous_department_id": previous_department_id,
         "department_id": claim.department_id, "department_name": destination,
         "department_response_due_at": claim.department_response_due_at.isoformat()},
        department_id=claim.department_id
    )
    db.commit()
    return {
        "ticket_id": ticket.id, "department_id": claim.department_id,
        "department_name": destination,
        "department_response_due_at": claim.department_response_due_at.isoformat() + "Z",
        "created_at": ticket.created_at.isoformat() + "Z",
        "sla_due_at": ticket.sla_due_at.isoformat() + "Z" if ticket.sla_due_at else None,
        "original_sla_preserved": True
    }


@router.get("/tickets/queue-summary")
def ticket_queue_summary(authorization: str | None = Header(default=None), db: Session = Depends(_db)):
    """Tenant-only pending ticket counts and waiting/department-response clocks."""
    user = _actor(authorization, db)
    from .models_growth import SupportTicket
    from .ticket_escalation_automation import TicketAutoEscalationClaim
    from .models_ai import Department

    now = datetime.utcnow()
    tickets = db.scalars(select(SupportTicket).where(
        SupportTicket.tenant_id == user.tenant_id,
        SupportTicket.status.notin_(("resolved", "closed"))
    ).order_by(SupportTicket.created_at.asc())).all()
    claims = db.scalars(select(TicketAutoEscalationClaim).where(
        TicketAutoEscalationClaim.tenant_id == user.tenant_id
    )).all()
    claim_by_ticket = {row.ticket_id: row for row in claims}
    departments = {row.id: row.name for row in db.scalars(select(Department).where(
        Department.tenant_id == user.tenant_id
    )).all()}
    counts = {}
    items = []
    for ticket in tickets:
        claim = claim_by_ticket.get(ticket.id)
        department_id = claim.department_id if claim else None
        key = department_id or "escalation"
        label = departments.get(department_id, "Escalation") if department_id else "Escalation"
        counts[key] = counts.get(key, {"department_id": department_id, "department_name": label, "pending_count": 0})
        counts[key]["pending_count"] += 1
        items.append({
            "ticket_id": ticket.id, "subject": ticket.subject, "category": ticket.category,
            "priority": ticket.priority, "status": ticket.status,
            "created_at": ticket.created_at.isoformat() + "Z",
            "waiting_seconds": max(0, int((now - ticket.created_at).total_seconds())),
            "sla_due_at": ticket.sla_due_at.isoformat() + "Z" if ticket.sla_due_at else None,
            "sla_breached": bool(ticket.sla_breached or (ticket.sla_due_at and ticket.sla_due_at <= now)),
            "department_id": department_id, "department_name": label,
            "department_response_due_at": claim.department_response_due_at.isoformat() + "Z" if claim else None,
        })
    return {"pending_by_department": list(counts.values()), "pending_count": len(items), "items": items}


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
