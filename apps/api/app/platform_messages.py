"""Platform → tenant messages.

SuperAdmin sends a message to a tenant. It appears in the tenant's
notification bell. Optionally also sends an email via Resend (if configured).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def send_message(
    db: Session,
    *,
    tenant_id: str,
    subject: str,
    body: str,
    from_admin_id: str | None = None,
    send_email: bool = True,
) -> dict:
    from .models_growth import PlatformMessage

    subject = (subject or "").strip()[:300]
    body = (body or "").strip()[:8000]
    if not subject:
        raise ValueError("subject is required")

    msg = PlatformMessage(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        subject=subject,
        body=body,
        from_admin_id=from_admin_id,
        email_sent=False,
        email_status=None,
        created_at=datetime.utcnow(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    email_status = "skipped"
    if send_email:
        try:
            email_status = _try_email(db, tenant_id, subject, body)
            msg.email_sent = email_status == "sent"
            msg.email_status = email_status
            db.commit()
        except Exception as exc:
            logger.debug("platform message email failed: %s", exc)
            msg.email_status = "error"
            db.commit()

    try:
        from .security import audit
        audit(
            db,
            tenant_id=tenant_id,
            actor_id=from_admin_id,
            action="platform.message_sent",
            target_type="tenant",
            target_id=tenant_id,
            detail={"subject": subject, "email_status": email_status},
        )
    except Exception:
        pass

    return _out(msg)


def _try_email(db: Session, tenant_id: str, subject: str, body: str) -> str:
    """Send email to the tenant owner. Returns a status string."""
    try:
        from .models import User, Tenant
        from .notifications import send_email as notif_send_email
    except Exception:
        return "not_configured"

    t = db.get(Tenant, tenant_id)
    if not t:
        return "tenant_not_found"

    owner = db.scalar(select(User).where(User.tenant_id == tenant_id, User.role.in_(["owner", "admin"])).limit(1))
    if not owner or not owner.email:
        return "no_owner_email"

    try:
        ok = notif_send_email(
            to_email=owner.email,
            subject=f"[AI Growth OS] {subject}",
            body=body,
        )
        return "sent" if ok else "failed"
    except Exception as exc:
        logger.debug("send_email exception: %s", exc)
        return "error"


def list_messages(db: Session, *, tenant_id: str | None = None, limit: int = 200) -> list:
    from .models_growth import PlatformMessage
    q = select(PlatformMessage)
    if tenant_id:
        q = q.where(PlatformMessage.tenant_id == tenant_id)
    rows = db.scalars(q.order_by(PlatformMessage.created_at.desc()).limit(min(max(limit, 1), 500))).all()
    return [_out(r) for r in rows]


def mark_read(db: Session, message_id: str) -> dict | None:
    from .models_growth import PlatformMessage
    m = db.get(PlatformMessage, message_id)
    if not m:
        return None
    m.read_at = datetime.utcnow()
    db.commit()
    db.refresh(m)
    return _out(m)


def _out(m) -> dict:
    return {
        "id": m.id,
        "tenant_id": m.tenant_id,
        "subject": m.subject,
        "body": m.body,
        "from_admin_id": m.from_admin_id,
        "read_at": m.read_at.isoformat() if m.read_at else None,
        "email_sent": bool(m.email_sent),
        "email_status": m.email_status,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }