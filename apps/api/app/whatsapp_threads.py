"""Group TenantWhatsAppMessage rows into chat threads keyed by phone number."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models_email import TenantWhatsAppMessage


def _contact_name(db: Session, tenant_id: str, phone: str) -> str | None:
    # Try to look up the display name from the tenant's contact book if present.
    try:
        from .models import Customer  # avoid circular import at module load
        c = db.scalar(select(Customer).where(
            Customer.tenant_id == tenant_id, Customer.phone == phone
        ))
        if c and c.name:
            return c.name
    except Exception:
        pass
    return None


def list_threads(db: Session, tenant_id: str, limit: int = 200) -> list[dict]:
    rows = db.scalars(
        select(TenantWhatsAppMessage)
        .where(TenantWhatsAppMessage.tenant_id == tenant_id)
        .order_by(TenantWhatsAppMessage.created_at.desc())
        .limit(max(1, min(limit * 20, 5000)))
    ).all()

    by_phone: dict[str, list] = defaultdict(list)
    for r in rows:
        by_phone[r.phone].append(r)

    threads: list[dict] = []
    for phone, msgs in by_phone.items():
        msgs.sort(key=lambda m: m.created_at or datetime.min)
        last = msgs[-1]
        unread = sum(1 for m in msgs if (m.direction or "") == "inbound" and (m.status or "") == "received")
        name = last.contact_name or _contact_name(db, tenant_id, phone)
        threads.append({
            "phone": phone,
            "contact_name": name,
            "last_at": (last.created_at or datetime.utcnow()).isoformat() + "Z",
            "last_body": (last.body or "")[:200],
            "last_direction": last.direction or "inbound",
            "message_count": len(msgs),
            "unread": unread,
        })

    threads.sort(key=lambda t: t["last_at"], reverse=True)
    return threads[:limit]


def thread_detail(db: Session, tenant_id: str, phone: str, limit: int = 300) -> dict | None:
    msgs = db.scalars(
        select(TenantWhatsAppMessage)
        .where(TenantWhatsAppMessage.tenant_id == tenant_id, TenantWhatsAppMessage.phone == phone)
        .order_by(TenantWhatsAppMessage.created_at.asc())
        .limit(max(1, min(limit, 1000)))
    ).all()
    if not msgs:
        return None
    name = msgs[-1].contact_name or _contact_name(db, tenant_id, phone)
    return {
        "phone": phone,
        "contact_name": name,
        "message_count": len(msgs),
        "messages": [
            {
                "id": m.id,
                "direction": m.direction or "inbound",
                "body": m.body or "",
                "status": m.status or "",
                "created_at": (m.created_at or datetime.utcnow()).isoformat() + "Z",
            }
            for m in msgs
        ],
    }