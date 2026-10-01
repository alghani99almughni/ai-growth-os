"""Platform calendar data.

Three layers:
    1. Signup anniversaries - tenants that joined on each day
    2. Activity heatmap - daily event counts per tenant
    3. Follow-up tasks - computed reminders (inactive tenants, breached
       SLAs, stuck orders, unpaid bills)
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, func
from sqlalchemy.orm import Session


def month_view(db: Session, year: int, month: int) -> dict:
    """Return events for every day in the given month."""
    from .models import Tenant
    from .models_growth import Order, CallRecord

    try:
        first = datetime(year, month, 1)
    except ValueError:
        raise ValueError("invalid year or month")

    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)

    days = []
    cursor = first
    while cursor < next_month:
        d_end = cursor + timedelta(days=1)

        signups = db.scalars(
            select(Tenant).where(
                Tenant.created_at >= cursor,
                Tenant.created_at < d_end,
            )
        ).all()

        orders = db.scalar(
            select(func.count(Order.id)).where(
                Order.created_at >= cursor, Order.created_at < d_end
            )
        ) or 0

        calls = db.scalar(
            select(func.count(CallRecord.id)).where(
                CallRecord.created_at >= cursor, CallRecord.created_at < d_end
            )
        ) or 0

        days.append({
            "date": cursor.date().isoformat(),
            "weekday": cursor.isoweekday(),  # 1=Mon ... 7=Sun
            "signups": [
                {"id": t.id, "name": t.name, "slug": t.slug, "industry": t.industry}
                for t in signups
            ],
            "orders": int(orders),
            "calls": int(calls),
            "total_events": len(signups) + int(orders) + int(calls),
        })
        cursor = d_end

    return {
        "year": year,
        "month": month,
        "first_day_weekday": first.isoweekday(),
        "days": days,
    }


def follow_ups(db: Session) -> dict:
    """Return three buckets of things needing attention."""
    from .models import Tenant
    from .models_growth import Order, CallRecord

    now = datetime.utcnow()
    thirty_days_ago = now - timedelta(days=30)

    inactive_tenants = []
    try:
        tenants = db.scalars(select(Tenant).where(Tenant.status == "active")).all()
        for t in tenants:
            last_calls = db.scalar(
                select(func.max(CallRecord.created_at)).where(CallRecord.tenant_id == t.id)
            )
            last_orders = db.scalar(
                select(func.max(Order.created_at)).where(Order.tenant_id == t.id)
            )
            last_activity = max([x for x in [last_calls, last_orders] if x] + [t.created_at]) if (last_calls or last_orders) else t.created_at
            if last_activity and last_activity < thirty_days_ago:
                inactive_tenants.append({
                    "tenant_id": t.id,
                    "name": t.name,
                    "last_activity": last_activity.isoformat() if last_activity else None,
                    "days_inactive": (now - last_activity).days,
                })
    except Exception:
        pass

    breached_tickets = []
    try:
        from .models_growth import SupportTicket
        rows = db.scalars(
            select(SupportTicket).where(
                SupportTicket.sla_breached == True,
                SupportTicket.status.in_(["new", "acknowledged", "in_progress", "waiting_on_tenant"]),
            ).limit(50)
        ).all()
        for r in rows:
            breached_tickets.append({
                "ticket_id": r.id,
                "tenant_id": r.tenant_id,
                "subject": r.subject,
                "category": r.category,
                "due_at": r.sla_due_at.isoformat() if r.sla_due_at else None,
            })
    except Exception:
        pass

    stuck_orders = []
    try:
        rows = db.scalars(
            select(Order).where(
                Order.status.in_(["confirmed", "preparing"]),
                Order.created_at < now - timedelta(hours=4),
            ).limit(50)
        ).all()
        for r in rows:
            stuck_orders.append({
                "order_id": r.id,
                "tenant_id": r.tenant_id,
                "status": r.status,
                "age_hours": int((now - r.created_at).total_seconds() / 3600),
            })
    except Exception:
        pass

    return {
        "inactive_tenants": inactive_tenants,
        "breached_tickets": breached_tickets,
        "stuck_orders": stuck_orders,
        "generated_at": now.isoformat(),
    }

def _with_ends(event: dict, default_minutes: int = 30) -> dict:
    """Add ends_at to an event dict based on at + duration_minutes."""
    from datetime import datetime as _dt
    try:
        start = _dt.fromisoformat(event["at"])
    except Exception:
        return event
    mins = int(event.get("duration_minutes") or default_minutes)
    event["ends_at"] = (start + timedelta(minutes=mins)).isoformat()
    event.setdefault("duration_minutes", mins)
    return event


def events_between(db: Session, start_iso: str, end_iso: str) -> list:
    """Return individual timestamped events between two ISO datetimes.

    Used by the Week and Day calendar views. Includes:
        - signups (Tenant.created_at)
        - calls (CallRecord.created_at)
        - orders (Order.created_at)
        - appointments (Appointment.created_at)
    """
    from datetime import datetime as _dt
    from .models import Tenant
    from .models_growth import Order, CallRecord, Appointment

    try:
        start = _dt.fromisoformat(start_iso)
        end = _dt.fromisoformat(end_iso)
    except (TypeError, ValueError):
        raise ValueError("start and end must be ISO datetimes")

    if end <= start:
        raise ValueError("end must be after start")

    events = []

    try:
        for t in db.scalars(select(Tenant).where(Tenant.created_at >= start, Tenant.created_at < end)).all():
            events.append({
                "at": t.created_at.isoformat(),
                "kind": "signup",
                "title": "New signup: " + (t.name or ""),
                "tenant_id": t.id,
                "link": "/platform/tenants/" + t.id,
                "meta": {"industry": t.industry},
            })
    except Exception:
        pass

    try:
        for c in db.scalars(select(CallRecord).where(CallRecord.created_at >= start, CallRecord.created_at < end)).all():
            title = "AI call"
            if c.summary:
                title = "Call: " + c.summary[:60]
            events.append({
                "at": c.created_at.isoformat(),
                "kind": "call",
                "title": title,
                "tenant_id": c.tenant_id,
                "link": "/platform/tenants/" + c.tenant_id,
                "meta": {"status": c.status, "language": c.language, "duration": c.duration_seconds},
            })
    except Exception:
        pass

    try:
        for o in db.scalars(select(Order).where(Order.created_at >= start, Order.created_at < end)).all():
            events.append({
                "at": o.created_at.isoformat(),
                "kind": "order",
                "title": "Order · " + str(o.total) + " INR",
                "tenant_id": o.tenant_id,
                "link": "/platform/tenants/" + o.tenant_id,
                "meta": {"status": o.status},
            })
    except Exception:
        pass

    try:
        for a in db.scalars(select(Appointment).where(Appointment.created_at >= start, Appointment.created_at < end)).all():
            events.append({
                "at": a.created_at.isoformat(),
                "kind": "appointment",
                "title": "Appointment booked",
                "tenant_id": a.tenant_id,
                "link": "/platform/tenants/" + a.tenant_id,
                "meta": {"status": a.status, "starts_at": a.starts_at.isoformat() if a.starts_at else None},
            })
    except Exception:
        pass

    try:
        from .models_growth import PlatformTask
        for task in db.scalars(select(PlatformTask).where(PlatformTask.due_at >= start, PlatformTask.due_at < end)).all():
            events.append({
                "at": task.due_at.isoformat(),
                "kind": "task",
                "title": ("✓ " if task.status == "done" else "") + task.title,
                "tenant_id": task.tenant_id,
                "link": "/platform/calendar",
                "duration_minutes": int(getattr(task, "duration_minutes", 30) or 30),
                "all_day": bool(getattr(task, "all_day", False)),
                "meta": {"status": task.status, "priority": task.priority, "task_id": task.id},
            })
    except Exception:
        pass

    events = [_with_ends(e) for e in events]
    events.sort(key=lambda x: x["at"])
    return events

