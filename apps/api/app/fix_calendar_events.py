"""Add an events-with-times endpoint to the calendar module."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
CAL = HERE / "calendar.py"

if not CAL.exists():
    print("ERROR: app/calendar.py not found")
    sys.exit(1)

text = CAL.read_text(encoding="utf-8")

if "def events_between" in text:
    print("SKIP: events_between already present")
    sys.exit(0)

NEW = '''

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

    events.sort(key=lambda x: x["at"])
    return events

'''

text = text.rstrip() + NEW
CAL.write_text(text, encoding="utf-8")
print("events_between added to calendar.py")