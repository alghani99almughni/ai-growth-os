"""Global platform settings.

One place for the platform owner to configure company info, SLA defaults,
alert channel toggles, and business hours. Read by other modules.

Settings are stored as rows in platform_settings (key, value_json).
Cache is in-process and invalidated on write.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULTS: dict[str, Any] = {
    # Company identity (used in outgoing emails/SMS/WhatsApp)
    "company_name": "AI Growth OS",
    "company_email": "hello@aigrowthos.com",
    "company_phone": "",
    "support_email": "support@aigrowthos.com",
    "billing_email": "billing@aigrowthos.com",
    "contact_email": "contact@aigrowthos.com",

    # SLA defaults per ticket category (hours)
    "sla_support_hours": 24,
    "sla_billing_hours": 4,
    "sla_contact_hours": 48,
    "sla_critical_hours": 2,

    # Alert channels (booleans)
    "alerts_email_enabled": True,
    "alerts_sms_enabled": False,
    "alerts_whatsapp_enabled": False,

    # Alert recipients (comma-separated)
    "alert_recipients": "",

    # Business hours (24h format strings)
    "business_hours_start": "09:00",
    "business_hours_end": "18:00",
    "business_days": "1,2,3,4,5",   # Monday=1 ... Sunday=7
    "timezone": "Asia/Kolkata",

    # Branding
    "brand_color": "#5b5cf0",
    "brand_logo_url": "",

    # Feature toggles for the whole platform
    "signups_enabled": True,
    "maintenance_mode": False,
    "maintenance_message": "We are performing scheduled maintenance. Please try again shortly.",
}


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------

def get_all(db: Session) -> dict:
    """Return every platform setting, merged with defaults.

    Missing keys fall back to DEFAULTS. So the API always returns a complete
    object even on a fresh install.
    """
    from .models_growth import PlatformSetting

    out = dict(DEFAULTS)
    try:
        rows = db.scalars(select(PlatformSetting)).all()
        for row in rows:
            try:
                out[row.key] = json.loads(row.value_json or "null")
            except Exception:
                out[row.key] = row.value_json
    except Exception as exc:
        logger.debug("get_all failed: %s", exc)
    return out


def get_one(db: Session, key: str, default: Any = None) -> Any:
    """Return a single setting value."""
    from .models_growth import PlatformSetting

    try:
        row = db.scalar(select(PlatformSetting).where(PlatformSetting.key == key))
        if row is None:
            return DEFAULTS.get(key, default)
        try:
            return json.loads(row.value_json or "null")
        except Exception:
            return row.value_json
    except Exception:
        return DEFAULTS.get(key, default)


def set_many(db: Session, updates: dict, actor_id: str | None = None) -> dict:
    """Update multiple settings at once. Only keys in DEFAULTS are stored."""
    from .models_growth import PlatformSetting

    now = datetime.utcnow()
    changed = []

    for key, value in (updates or {}).items():
        if key not in DEFAULTS:
            continue  # ignore unknown keys — never silently store junk
        row = db.scalar(select(PlatformSetting).where(PlatformSetting.key == key))
        payload = json.dumps(value)
        if row is None:
            db.add(PlatformSetting(
                id=str(uuid.uuid4()),
                key=key,
                value_json=payload,
                updated_at=now,
                updated_by=actor_id,
            ))
        else:
            row.value_json = payload
            row.updated_at = now
            row.updated_by = actor_id
        changed.append(key)

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("set_many failed: %s", exc)
        raise

    try:
        from .security import audit
        audit(
            db,
            tenant_id=None,
            actor_id=actor_id,
            action="platform.settings_updated",
            target_type="platform",
            target_id="settings",
            detail={"keys": changed},
        )
    except Exception:
        pass

    return get_all(db)


# ---------------------------------------------------------------------------
# SLA helpers
# ---------------------------------------------------------------------------

def sla_hours_for_category(db: Session, category: str) -> int:
    """Return the SLA window in hours for a ticket category."""
    category = (category or "support").lower()
    key = {
        "support": "sla_support_hours",
        "billing": "sla_billing_hours",
        "contact": "sla_contact_hours",
        "critical": "sla_critical_hours",
    }.get(category, "sla_support_hours")

    try:
        return max(1, int(get_one(db, key, DEFAULTS[key])))
    except Exception:
        return int(DEFAULTS[key])


def is_within_business_hours(db: Session, when: datetime | None = None) -> bool:
    """Whether `when` (default now) falls within configured business hours."""
    try:
        start = str(get_one(db, "business_hours_start", "09:00"))
        end = str(get_one(db, "business_hours_end", "18:00"))
        days = str(get_one(db, "business_days", "1,2,3,4,5"))
    except Exception:
        return True

    when = when or datetime.utcnow()
    try:
        start_t = time.fromisoformat(start)
        end_t = time.fromisoformat(end)
    except Exception:
        return True

    allowed_days = {int(x) for x in days.split(",") if x.strip().isdigit()}
    iso_weekday = when.isoweekday()  # 1=Mon ... 7=Sun
    if iso_weekday not in allowed_days:
        return False
    return start_t <= when.time() <= end_t


# ---------------------------------------------------------------------------
# Quick status (used by the settings API)
# ---------------------------------------------------------------------------

def status(db: Session) -> dict:
    s = get_all(db)
    return {
        "company_name": s.get("company_name"),
        "support_email": s.get("support_email"),
        "maintenance_mode": bool(s.get("maintenance_mode")),
        "signups_enabled": bool(s.get("signups_enabled")),
        "alerts_email_enabled": bool(s.get("alerts_email_enabled")),
        "alerts_sms_enabled": bool(s.get("alerts_sms_enabled")),
        "alerts_whatsapp_enabled": bool(s.get("alerts_whatsapp_enabled")),
        "timezone": s.get("timezone"),
    }