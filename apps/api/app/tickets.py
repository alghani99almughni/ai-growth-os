"""Support ticket engine.

Tenants submit tickets. SuperAdmin manages them. Each ticket has an SLA
window based on category (support/billing/contact/critical). SLA breach is
computed live from sla_due_at; the DB flag is a denormalized cache.

Ticket states:
    new                -> just submitted
    acknowledged       -> admin saw it
    in_progress        -> admin is working
    waiting_on_tenant  -> admin asked, waiting for reply
    resolved           -> admin finished
    closed             -> auto-closed after idle (or manual)

SLA is set from platform_settings (sla_support_hours etc.) at creation time.
It's NOT recalculated if the setting changes later, so existing tickets keep
their original commitment.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


STATES = ("new", "acknowledged", "in_progress", "waiting_on_tenant", "resolved", "closed")
OPEN_STATES = ("new", "acknowledged", "in_progress", "waiting_on_tenant")
CATEGORIES = ("support", "billing", "contact", "critical")
PRIORITIES = ("low", "normal", "high", "urgent")


# ---------------------------------------------------------------------------
# Model accessor (class is defined in models_growth when migration runs)
# ---------------------------------------------------------------------------

def _model():
    from .models_growth import SupportTicket
    return SupportTicket


# ---------------------------------------------------------------------------
# SLA
# ---------------------------------------------------------------------------

def _compute_sla_hours(db: Session, category: str) -> int:
    try:
        from .platform_settings import sla_hours_for_category
        return sla_hours_for_category(db, category)
    except Exception:
        return 24


def _is_breached(ticket) -> bool:
    if not getattr(ticket, "sla_due_at", None):
        return False
    if ticket.status in ("resolved", "closed"):
        return False
    return datetime.utcnow() > ticket.sla_due_at


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def create_ticket(
    db: Session,
    *,
    tenant_id: str,
    subject: str,
    body: str = "",
    category: str = "support",
    priority: str = "normal",
    created_by: str | None = None,
    sla_hours_override: int | None = None,
) -> dict:
    """Create a new support ticket with SLA clock started."""
    M = _model()

    subject = (subject or "").strip()[:300]
    if not subject:
        raise ValueError("subject is required")

    category = (category or "support").lower()
    if category not in CATEGORIES:
        category = "support"

    priority = (priority or "normal").lower()
    if priority not in PRIORITIES:
        priority = "normal"

    sla_hours = sla_hours_override or _compute_sla_hours(db, category)
    now = datetime.utcnow()
    due = now + timedelta(hours=sla_hours)

    ticket = M(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        subject=subject,
        body=(body or "")[:8000],
        category=category,
        priority=priority,
        status="new",
        sla_hours=sla_hours,
        sla_due_at=due,
        sla_breached=False,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    try:
        from .security import audit
        audit(
            db,
            tenant_id=tenant_id,
            actor_id=created_by,
            action="ticket.created",
            target_type="ticket",
            target_id=ticket.id,
            detail={"category": category, "priority": priority, "sla_hours": sla_hours},
        )
    except Exception:
        pass

    return _out(ticket)


# ---------------------------------------------------------------------------
# List / get
# ---------------------------------------------------------------------------

def list_tickets(
    db: Session,
    *,
    tenant_id: str | None = None,
    status: str | None = None,
    category: str | None = None,
    include_breached_only: bool = False,
    limit: int = 200,
) -> list:
    M = _model()
    q = select(M)
    if tenant_id:
        q = q.where(M.tenant_id == tenant_id)
    if status:
        if status == "open":
            q = q.where(M.status.in_(OPEN_STATES))
        else:
            q = q.where(M.status == status)
    if category:
        q = q.where(M.category == category)

    rows = db.scalars(q.order_by(M.created_at.desc()).limit(min(max(limit, 1), 500))).all()

    # Recompute breach flag live
    for r in rows:
        live = _is_breached(r)
        if live != bool(getattr(r, "sla_breached", False)):
            try:
                r.sla_breached = live
                db.commit()
            except Exception:
                db.rollback()

    if include_breached_only:
        rows = [r for r in rows if getattr(r, "sla_breached", False)]

    return [_out(r) for r in rows]


def get_ticket(db: Session, ticket_id: str) -> dict | None:
    M = _model()
    t = db.get(M, ticket_id)
    if not t:
        return None
    return _out(t)


# ---------------------------------------------------------------------------
# Update status
# ---------------------------------------------------------------------------

def set_status(db: Session, ticket_id: str, status: str, actor_id: str | None = None) -> dict:
    M = _model()
    if status not in STATES:
        raise ValueError(f"status must be one of: {', '.join(STATES)}")

    t = db.get(M, ticket_id)
    if not t:
        raise ValueError("ticket not found")

    prev = t.status
    t.status = status
    t.updated_at = datetime.utcnow()

    if status in ("resolved", "closed"):
        t.resolved_at = t.resolved_at or datetime.utcnow()
        t.resolved_by = actor_id

    db.commit()
    db.refresh(t)

    try:
        from .security import audit
        audit(
            db,
            tenant_id=t.tenant_id,
            actor_id=actor_id,
            action="ticket.status_changed",
            target_type="ticket",
            target_id=t.id,
            detail={"from": prev, "to": status},
        )
    except Exception:
        pass

    return _out(t)


def assign(db: Session, ticket_id: str, staff_user_id: str | None, actor_id: str | None = None) -> dict:
    M = _model()
    t = db.get(M, ticket_id)
    if not t:
        raise ValueError("ticket not found")
    t.assigned_to = staff_user_id
    t.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(t)
    return _out(t)


# ---------------------------------------------------------------------------
# Reply (appends to body thread and changes state)
# ---------------------------------------------------------------------------

def reply(
    db: Session,
    ticket_id: str,
    message: str,
    *,
    from_tenant: bool = False,
    actor_id: str | None = None,
) -> dict:
    M = _model()
    t = db.get(M, ticket_id)
    if not t:
        raise ValueError("ticket not found")

    stamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    role = "Tenant" if from_tenant else "Support"
    entry = f"\n\n---\n[{stamp} · {role}]\n{(message or '').strip()}"

    t.body = (t.body or "") + entry
    t.updated_at = datetime.utcnow()

    # Auto state transitions
    if from_tenant and t.status in ("waiting_on_tenant", "resolved"):
        t.status = "acknowledged"
    elif not from_tenant and t.status == "new":
        t.status = "acknowledged"

    db.commit()
    db.refresh(t)

    try:
        from .security import audit
        audit(
            db,
            tenant_id=t.tenant_id,
            actor_id=actor_id,
            action="ticket.replied",
            target_type="ticket",
            target_id=t.id,
            detail={"from_tenant": from_tenant, "new_status": t.status},
        )
    except Exception:
        pass

    return _out(t)


# ---------------------------------------------------------------------------
# SLA dashboard
# ---------------------------------------------------------------------------

def sla_summary(db: Session, tenant_id: str | None = None) -> dict:
    """Return counts of open/breached/at-risk tickets."""
    M = _model()
    q = select(M).where(M.status.in_(OPEN_STATES))
    if tenant_id:
        q = q.where(M.tenant_id == tenant_id)
    rows = db.scalars(q).all()

    now = datetime.utcnow()
    open_count = len(rows)
    breached = sum(1 for r in rows if _is_breached(r))
    due_soon = 0
    for r in rows:
        if r.sla_due_at and not _is_breached(r):
            delta = (r.sla_due_at - now).total_seconds()
            if delta <= 3600:
                due_soon += 1

    return {
        "open": open_count,
        "breached": breached,
        "due_within_hour": due_soon,
        "healthy": max(0, open_count - breached - due_soon),
    }


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def _out(t) -> dict:
    breach = _is_breached(t)
    now = datetime.utcnow()
    remaining = None
    if t.sla_due_at and t.status not in ("resolved", "closed"):
        remaining = int((t.sla_due_at - now).total_seconds())

    return {
        "id": t.id,
        "tenant_id": t.tenant_id,
        "subject": t.subject,
        "body": t.body or "",
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "sla_hours": t.sla_hours,
        "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None,
        "sla_remaining_seconds": remaining,
        "sla_breached": breach,
        "assigned_to": t.assigned_to,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
        "resolved_by": t.resolved_by,
    }