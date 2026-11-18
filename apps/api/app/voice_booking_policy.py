"""Tenant-configurable last-minute booking and human callback policy.

This module is deliberately side-effect free for booking decisions. It uses the
call's persisted start timestamp (not the current turn time) and tenant-local
business hours. Callback persistence/notification is handled by the call workflow.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Tenant
from .models_growth import BusinessHour, TenantSetting

SETTING_KEY = "voice_booking_policy"
DEFAULT_WINDOW_MINUTES = 30
ALLOWED_WINDOW_MINUTES = (15, 30)


@dataclass(frozen=True)
class LastMinuteDecision:
    is_last_minute: bool
    window_minutes: int
    minutes_until_close: int | None
    reason: str


def get_voice_booking_policy(db: Session, tenant_id: str) -> dict:
    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == SETTING_KEY,
    ))
    import json
    try:
        value = json.loads(row.value_json) if row else {}
    except (TypeError, ValueError):
        value = {}
    window = value.get("last_minute_window_minutes", DEFAULT_WINDOW_MINUTES)
    if window not in ALLOWED_WINDOW_MINUTES:
        window = DEFAULT_WINDOW_MINUTES
    return {
        "last_minute_window_minutes": window,
        "handoff_enabled": bool(value.get("handoff_enabled", True)),
    }


def save_voice_booking_policy(db: Session, tenant_id: str, window_minutes: int) -> dict:
    if window_minutes not in ALLOWED_WINDOW_MINUTES:
        raise ValueError("Last-minute window must be 15 or 30 minutes.")
    import json
    row = db.scalar(select(TenantSetting).where(
        TenantSetting.tenant_id == tenant_id,
        TenantSetting.key == SETTING_KEY,
    ))
    if row is None:
        row = TenantSetting(tenant_id=tenant_id, key=SETTING_KEY)
        db.add(row)
    row.value_json = json.dumps({
        "last_minute_window_minutes": window_minutes,
        "handoff_enabled": True,
    })
    db.commit()
    return get_voice_booking_policy(db, tenant_id)


def evaluate_last_minute(
    db: Session,
    tenant: Tenant,
    call_started_at_utc: datetime,
    requested_day: date,
    requested_time: time,
) -> LastMinuteDecision:
    """Evaluate same-day request against that day's close, using call-start time.

    Naive persisted datetimes in this application represent UTC. A request is
    considered last-minute only when the call began on the requested local date
    and the call began within the configured closing buffer.
    """
    policy = get_voice_booking_policy(db, tenant.id)
    window = policy["last_minute_window_minutes"]
    tz = ZoneInfo(tenant.timezone or "Asia/Kolkata")
    started = call_started_at_utc
    if started.tzinfo is None:
        started = started.replace(tzinfo=ZoneInfo("UTC"))
    local_start = started.astimezone(tz)
    if local_start.date() != requested_day:
        return LastMinuteDecision(False, window, None, "not_same_day")

    hours = db.scalar(select(BusinessHour).where(
        BusinessHour.tenant_id == tenant.id,
        BusinessHour.weekday == requested_day.weekday(),
    ))
    if hours is None or hours.is_closed:
        return LastMinuteDecision(False, window, None, "closed_or_unconfigured")
    close_dt = datetime.combine(requested_day, hours.close_time, tzinfo=tz)
    minutes_left = int((close_dt - local_start).total_seconds() // 60)
    if minutes_left < 0:
        return LastMinuteDecision(False, window, minutes_left, "call_started_after_close")
    if minutes_left <= window:
        return LastMinuteDecision(True, window, minutes_left, "inside_last_minute_window")
    return LastMinuteDecision(False, window, minutes_left, "outside_last_minute_window")
