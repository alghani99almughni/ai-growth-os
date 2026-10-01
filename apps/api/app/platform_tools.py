"""SuperAdmin platform tools.

Everything the /platform console needs:
    - Tenant list with health score
    - Growth chart data
    - Per-tenant feature overrides
    - WhatsApp / Razorpay status (masked secrets)
    - Per-tenant activity metrics
    - Admin QR generation on behalf of a tenant

Every function is scoped to a tenant_id and does NOT bypass tenant isolation
unless the caller is verified platform_admin. Callers must check role.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tenant list
# ---------------------------------------------------------------------------

def list_tenants(db: Session, *, search: str = "", status: str = "", limit: int = 500) -> list:
    """Return tenants with computed health score and last-seen time."""
    from .models import Tenant

    q = select(Tenant)
    if status:
        q = q.where(Tenant.status == status)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(
            func.lower(Tenant.name).like(like) | func.lower(Tenant.slug).like(like)
        )
    rows = db.scalars(q.order_by(Tenant.created_at.desc()).limit(min(max(limit, 1), 1000))).all()

    out = []
    for t in rows:
        try:
            score = tenant_health_score(db, t.id)
        except Exception:
            score = {"score": 50, "band": "unknown", "reasons": []}
        out.append({
            "id": t.id,
            "name": t.name,
            "slug": t.slug,
            "industry": t.industry,
            "status": t.status,
            "plan": getattr(t, "plan", None),
            "city": getattr(t, "city", None),
            "phone": getattr(t, "phone", None),
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "last_seen_at": (
                t.last_seen_at.isoformat()
                if getattr(t, "last_seen_at", None) else None
            ),
            "health_status": getattr(t, "health_status", "unknown"),
            "region": getattr(t, "region", "GLOBAL"),
            "health_score": score["score"],
            "health_band": score["band"],
        })
    return out


# ---------------------------------------------------------------------------
# Health score
# ---------------------------------------------------------------------------

def tenant_health_score(db: Session, tenant_id: str) -> dict:
    """Compute a 0-100 health score for a tenant.

    Weighted blend of:
        - Days since last customer activity  (20%)
        - Days since last admin login        (20%)
        - AI requests in last 7 days         (15%)
        - Failed API calls last 7 days       (15%)
        - Feature adoption                   (15%)
        - Open tickets                       (15%)
    """
    from .models import Customer, Lead
    from .models_growth import Order, CallRecord, TenantSetting

    now = datetime.utcnow()
    score = 0.0
    reasons = []

    # 1. customer activity (20 pts)
    try:
        last_cust = db.scalar(
            select(func.max(Customer.created_at)).where(Customer.tenant_id == tenant_id)
        )
        if last_cust:
            days = (now - last_cust).days
            if days <= 1:
                score += 20
            elif days <= 7:
                score += 15
            elif days <= 30:
                score += 10
            else:
                score += 3
                reasons.append(f"no customer activity for {days} days")
        else:
            reasons.append("no customers yet")
    except Exception:
        pass

    # 2. admin login (20 pts)
    try:
        from .models import User
        last_login = db.scalar(
            select(func.max(Tenant.created_at)).where(Tenant.id == tenant_id)
        )
        # Use the tenant's last_seen_at if present
        from .models import Tenant as T
        t = db.get(T, tenant_id)
        if t and getattr(t, "last_seen_at", None):
            days = (now - t.last_seen_at).days
            if days <= 1:
                score += 20
            elif days <= 7:
                score += 15
            elif days <= 30:
                score += 8
            else:
                score += 2
                reasons.append(f"admin not seen for {days} days")
        else:
            score += 5
            reasons.append("admin has never logged in via the API")
    except Exception:
        score += 10

    # 3. AI activity last 7 days (15 pts)
    try:
        since = now - timedelta(days=7)
        calls = db.scalar(
            select(func.count(CallRecord.id)).where(
                CallRecord.tenant_id == tenant_id,
                CallRecord.created_at >= since,
            )
        ) or 0
        if calls >= 20:
            score += 15
        elif calls >= 5:
            score += 10
        elif calls >= 1:
            score += 6
        else:
            score += 0
            reasons.append("no AI calls in last 7 days")
    except Exception:
        pass

    # 4. error rate (15 pts)
    try:
        from .models_growth import AuditLog
        since = now - timedelta(days=7)
        errors = db.scalar(
            select(func.count(AuditLog.id)).where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.action.like("error%"),
                AuditLog.created_at >= since,
            )
        ) or 0
        if errors == 0:
            score += 15
        elif errors <= 3:
            score += 10
        elif errors <= 10:
            score += 5
        else:
            reasons.append(f"{errors} errors in last 7 days")
    except Exception:
        score += 10

    # 5. feature adoption (15 pts)
    try:
        row = db.scalar(select(TenantSetting).where(
            TenantSetting.tenant_id == tenant_id,
            TenantSetting.key == "features",
        ))
        features = json.loads(row.value_json or "{}") if row else {}
        enabled = sum(1 for v in features.values() if v)
        total = len(features) or 1
        score += int(15 * (enabled / total))
        if enabled < 3:
            reasons.append(f"only {enabled} features enabled")
    except Exception:
        pass

    # 6. tickets (15 pts) — placeholder until 17b
    try:
        from .models_growth import SupportTicket
        open_count = db.scalar(
            select(func.count(SupportTicket.id)).where(
                SupportTicket.tenant_id == tenant_id,
                SupportTicket.status.in_(["new", "acknowledged", "in_progress", "waiting_on_tenant"]),
            )
        ) or 0
        if open_count == 0:
            score += 15
        elif open_count <= 2:
            score += 10
        else:
            score += 3
            reasons.append(f"{open_count} open tickets")
    except Exception:
        score += 15  # no ticket table yet — award full points

    score = max(0, min(100, int(round(score))))
    if score >= 80:
        band = "healthy"
    elif score >= 60:
        band = "watch"
    elif score >= 40:
        band = "at_risk"
    else:
        band = "critical"

    return {"score": score, "band": band, "reasons": reasons}


# ---------------------------------------------------------------------------
# Growth chart
# ---------------------------------------------------------------------------

def overview(db: Session, *, days: int = 30) -> dict:
    """KPIs + signup chart for the platform overview page."""
    from .models import Tenant, Customer, Lead
    from .models_growth import Order, CallRecord

    days = min(max(int(days), 7), 365)
    since = datetime.utcnow() - timedelta(days=days)

    total_tenants = db.scalar(select(func.count(Tenant.id))) or 0
    active_tenants = db.scalar(
        select(func.count(Tenant.id)).where(Tenant.status == "active")
    ) or 0

    recent_signups = db.scalars(
        select(Tenant).where(Tenant.created_at >= since).order_by(Tenant.created_at.desc()).limit(10)
    ).all()

    # Signups per day
    rows = db.execute(
        select(
            func.date(Tenant.created_at).label("d"),
            func.count(Tenant.id),
        )
        .where(Tenant.created_at >= since)
        .group_by("d")
        .order_by("d")
    ).all()
    signups_per_day = [{"date": str(r[0]), "count": int(r[1])} for r in rows]

    total_customers = db.scalar(select(func.count(Customer.id))) or 0
    total_leads = db.scalar(select(func.count(Lead.id))) or 0
    total_orders = db.scalar(select(func.count(Order.id))) or 0
    total_calls = db.scalar(select(func.count(CallRecord.id))) or 0

    return {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "total_customers": total_customers,
        "total_leads": total_leads,
        "total_orders": total_orders,
        "total_calls": total_calls,
        "signups_per_day": signups_per_day,
        "recent_signups": [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "industry": t.industry,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in recent_signups
        ],
    }


# ---------------------------------------------------------------------------
# Feature overrides
# ---------------------------------------------------------------------------

def get_overrides(db: Session, tenant_id: str) -> dict:
    """Read the tenant's feature overrides."""
    from .models_growth import TenantSetting
    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == "features",
    ))
    try:
        return json.loads(row.value_json or "{}") if row else {}
    except Exception:
        return {}


def set_overrides(db: Session, tenant_id: str, overrides: dict, actor_id: str | None = None) -> dict:
    """Set a tenant's feature overrides. SuperAdmin path — bypasses tenant checks."""
    from .models_growth import TenantSetting

    # Only allow known feature keys to be set
    allowed = {
        "digital_menu", "online_ordering", "order_tracking", "call_waiter",
        "service_requests", "games", "auto_bill", "online_payment",
        "ai_chat", "ai_voice", "loyalty", "referrals", "feedback",
        "google_review", "bookings", "queue",
    }
    cleaned = {k: bool(v) for k, v in (overrides or {}).items() if k in allowed}

    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == "features",
    ))
    payload = json.dumps(cleaned)
    if row:
        row.value_json = payload
    else:
        db.add(TenantSetting(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            key="features",
            value_json=payload,
        ))
    db.commit()

    try:
        from .security import audit
        audit(
            db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="platform.feature_overrides_set",
            target_type="tenant",
            target_id=tenant_id,
            detail={"overrides": cleaned},
        )
    except Exception:
        pass

    return cleaned


# ---------------------------------------------------------------------------
# WhatsApp status
# ---------------------------------------------------------------------------

def whatsapp_status(db: Session, tenant_id: str) -> dict:
    """Return both channels' status with masked credentials."""
    from .whatsapp_channels import all_channels
    try:
        state = all_channels(db, tenant_id)
    except Exception as exc:
        logger.debug("all_channels failed: %s", exc)
        state = {
            "openwa": {"provider": "openwa", "connected": False, "status": "disconnected"},
            "meta": {"provider": "meta", "connected": False, "status": "disconnected"},
            "priority": "openwa",
            "active": None,
        }
    # Never return the raw config
    return state


# ---------------------------------------------------------------------------
# Razorpay status
# ---------------------------------------------------------------------------

def razorpay_status(db: Session, tenant_id: str) -> dict:
    """Return the tenant's Razorpay status with a masked key_id."""
    from .models_integrations import TenantIntegration
    from .integrations import decrypt_channel_config
    from .config import settings

    out = {
        "connected": False,
        "key_id_masked": None,
        "webhook_configured": False,
        "last_payment_at": None,
        "recent_failures": 0,
    }

    row = db.scalar(select(TenantIntegration).where(
        TenantIntegration.tenant_id == tenant_id,
        TenantIntegration.integration_key == "razorpay",
        TenantIntegration.status == "connected",
    ))
    if not row:
        return out

    out["connected"] = True
    out["webhook_configured"] = True  # set true by configure endpoint
    try:
        key = settings.integration_credential_encryption_key or settings.whatsapp_credential_encryption_key
        cfg = decrypt_channel_config(row.config_encrypted, key)
        kid = cfg.get("key_id") or ""
        if kid:
            out["key_id_masked"] = kid[:6] + "…" + kid[-4:] if len(kid) > 10 else "***"
    except Exception as exc:
        logger.debug("razorpay_status decrypt failed: %s", exc)

    # Last payment
    try:
        from .models_growth import Bill
        last = db.scalar(
            select(func.max(Bill.paid_at)).where(
                Bill.tenant_id == tenant_id, Bill.status == "paid"
            )
        )
        if last:
            out["last_payment_at"] = last.isoformat()
    except Exception:
        pass

    return out


# ---------------------------------------------------------------------------
# Activity metrics
# ---------------------------------------------------------------------------

def activity_metrics(db: Session, tenant_id: str, *, days: int = 30) -> dict:
    """Return 30-day usage metrics for a tenant."""
    from .models import Customer, Lead
    from .models_growth import Order, CallRecord, Appointment

    days = min(max(int(days), 1), 365)
    since = datetime.utcnow() - timedelta(days=days)

    def _count(model, *extra):
        try:
            q = select(func.count(model.id)).where(
                model.tenant_id == tenant_id,
                model.created_at >= since,
                *extra,
            )
            return int(db.scalar(q) or 0)
        except Exception:
            return 0

    customers = _count(Customer)
    leads = _count(Lead)
    orders = _count(Order)
    calls = _count(CallRecord)
    try:
        appts = db.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.tenant_id == tenant_id,
                Appointment.created_at >= since,
            )
        ) or 0
    except Exception:
        appts = 0

    # Per-day order counts for the mini chart
    rows = db.execute(
        select(func.date(Order.created_at).label("d"), func.count(Order.id))
        .where(Order.tenant_id == tenant_id, Order.created_at >= since)
        .group_by("d")
        .order_by("d")
    ).all()
    orders_per_day = [{"date": str(r[0]), "count": int(r[1])} for r in rows]

    return {
        "days": days,
        "customers": customers,
        "leads": leads,
        "orders": orders,
        "calls": calls,
        "appointments": int(appts),
        "orders_per_day": orders_per_day,
    }


# ---------------------------------------------------------------------------
# Admin QR generation
# ---------------------------------------------------------------------------

def admin_create_qr(
    db: Session,
    tenant_id: str,
    *,
    kind: str = "business",
    label: str = "Admin generated QR",
    context_type: Optional[str] = None,
    context_value: Optional[str] = None,
    campaign_id: Optional[str] = None,
    admin_id: Optional[str] = None,
    public_base: str = "",
) -> dict:
    """Create a QR on behalf of a tenant. Records admin_id in the audit log."""
    from .qr import create_qr
    from .security import audit

    entry = create_qr(
        db, tenant_id,
        kind=kind, label=label,
        context_type=context_type, context_value=context_value,
        campaign_id=campaign_id,
        created_by=admin_id,
        public_base=public_base,
    )

    try:
        audit(
            db,
            tenant_id=tenant_id,
            actor_id=admin_id,
            action="platform.qr_created_for_tenant",
            target_type="qr",
            target_id=entry["id"],
            detail={"kind": entry["kind"], "label": entry["label"]},
        )
    except Exception:
        pass

    return entry


# ---------------------------------------------------------------------------
# Update last_seen_at (called on tenant login)
# ---------------------------------------------------------------------------

def mark_tenant_seen(db: Session, tenant_id: str) -> None:
    """Update tenants.last_seen_at. Never raises."""
    from .models import Tenant
    try:
        t = db.get(Tenant, tenant_id)
        if t:
            t.last_seen_at = datetime.utcnow()
            t.health_status = "seen"
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass