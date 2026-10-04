"""Platform-wide email + WhatsApp overview.

Super Admin uses this to see every tenant's communication channels at once.

Endpoints:
    GET  /api/v1/platform/email/overview       all tenants + email accounts
    GET  /api/v1/platform/whatsapp/overview    all tenants + WhatsApp status
    GET  /api/v1/platform/comms/health         poller + channel health summary
"""
from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from .models import Tenant
from .models_email import TenantEmailAccount, EmailLog
from .models_integrations import TenantIntegration
from .security import decode_token_strict
from .config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth (reuse main.get_current_user shape but standalone)
# ---------------------------------------------------------------------------

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .db import SessionLocal
from .models import User

_bearer = HTTPBearer(auto_error=False)


def _db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _require_platform_admin(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(_db),
):
    if creds is None:
        raise HTTPException(401, "Authentication required")
    try:
        p = decode_token_strict(creds.credentials, settings.jwt_secret, settings.jwt_algorithm)
    except ValueError as exc:
        raise HTTPException(401, str(exc))
    user = db.get(User, p.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(401, "Invalid user")
    if user.role not in ("platform_admin", "super_admin"):
        raise HTTPException(403, "Platform admin access required")
    return user


# ---------------------------------------------------------------------------
# Email overview
# ---------------------------------------------------------------------------

@router.get("/api/v1/platform/email/overview")
def email_overview(
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    """Every tenant with its email accounts, poller state, and recent activity."""
    tenants = db.scalars(select(Tenant).order_by(Tenant.name)).all()
    tenant_ids = [t.id for t in tenants]

    accounts = db.scalars(
        select(TenantEmailAccount).where(TenantEmailAccount.tenant_id.in_(tenant_ids))
    ).all() if tenant_ids else []

    by_tenant: dict[str, list] = {}
    for a in accounts:
        by_tenant.setdefault(a.tenant_id, []).append(a)

    # Last 24h log counts per tenant
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(hours=24)
    log_rows = db.execute(
        select(EmailLog.tenant_id, EmailLog.outcome, func.count(EmailLog.id))
        .where(EmailLog.created_at >= since)
        .group_by(EmailLog.tenant_id, EmailLog.outcome)
    ).all()
    log_stats: dict[str, dict] = {}
    for tid, outcome, count in log_rows:
        log_stats.setdefault(tid, {})[outcome or "unknown"] = int(count)

    items = []
    for t in tenants:
        accs = by_tenant.get(t.id, [])
        items.append({
            "tenant_id": t.id,
            "tenant_name": t.name,
            "tenant_slug": t.slug,
            "industry": t.industry,
            "status": t.status,
            "account_count": len(accs),
            "active_count": sum(1 for a in accs if a.is_active),
            "auto_reply_count": sum(1 for a in accs if a.auto_reply_enabled),
            "accounts": [
                {
                    "id": a.id,
                    "label": a.label,
                    "provider": a.provider,
                    "email_address": a.email_address,
                    "role": a.role,
                    "is_active": a.is_active,
                    "auto_reply_enabled": a.auto_reply_enabled,
                    "last_checked_at": a.last_checked_at.isoformat() if a.last_checked_at else None,
                    "last_error": a.last_error,
                }
                for a in accs
            ],
            "activity_24h": log_stats.get(t.id, {}),
        })

    totals = {
        "tenants": len(tenants),
        "tenants_with_email": sum(1 for x in items if x["account_count"] > 0),
        "total_accounts": sum(x["account_count"] for x in items),
        "total_active": sum(x["active_count"] for x in items),
        "total_errors": sum(1 for x in items for a in x["accounts"] if a["last_error"]),
    }
    return {"totals": totals, "items": items}


# ---------------------------------------------------------------------------
# WhatsApp overview
# ---------------------------------------------------------------------------

@router.get("/api/v1/platform/whatsapp/overview")
def whatsapp_overview(
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    """Every tenant with its WhatsApp channel state."""
    tenants = db.scalars(select(Tenant).order_by(Tenant.name)).all()

    try:
        from .whatsapp_channels import all_channels
    except Exception:
        all_channels = None

    items = []
    for t in tenants:
        state = None
        if all_channels:
            try:
                state = all_channels(db, t.id)
            except Exception as exc:
                logger.debug("all_channels failed for %s: %s", t.id, exc)

        openwa = (state or {}).get("openwa") or {}
        meta = (state or {}).get("meta") or {}

        items.append({
            "tenant_id": t.id,
            "tenant_name": t.name,
            "tenant_slug": t.slug,
            "industry": t.industry,
            "status": t.status,
            "openwa_connected": bool(openwa.get("connected")),
            "openwa_status": openwa.get("status"),
            "openwa_phone": openwa.get("connected_phone"),
            "meta_connected": bool(meta.get("connected")),
            "meta_status": meta.get("status"),
            "meta_phone": meta.get("connected_phone"),
            "priority": (state or {}).get("priority") or "openwa",
            "active": (state or {}).get("active"),
        })

    totals = {
        "tenants": len(tenants),
        "with_openwa": sum(1 for x in items if x["openwa_connected"]),
        "with_meta": sum(1 for x in items if x["meta_connected"]),
        "with_any_channel": sum(1 for x in items if x["openwa_connected"] or x["meta_connected"]),
    }
    return {"totals": totals, "items": items}


# ---------------------------------------------------------------------------
# Comms health summary
# ---------------------------------------------------------------------------

@router.get("/api/v1/platform/comms/health")
def comms_health(
    user=Depends(_require_platform_admin),
    db: Session = Depends(_db),
):
    """Pollers and integrations — quick health glance."""
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(hours=1)

    try:
        from .email_poller import _poller_task
        poller_running = bool(_poller_task and not _poller_task.done())
    except Exception:
        poller_running = None

    email_processed_1h = db.scalar(
        select(func.count(EmailLog.id)).where(EmailLog.created_at >= since)
    ) or 0

    integrations = db.scalar(
        select(func.count(TenantIntegration.id))
        .where(TenantIntegration.status == "connected")
    ) or 0

    return {
        "email_poller_running": poller_running,
        "email_processed_last_1h": int(email_processed_1h),
        "connected_integrations": int(integrations),
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }