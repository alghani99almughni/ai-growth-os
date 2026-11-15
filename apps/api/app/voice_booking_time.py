"""Deterministic call-time and AM/PM resolution for voice booking.

All naive CallRecord timestamps are UTC by project convention.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


def call_local_datetime(started_at: datetime, timezone_name: str) -> datetime:
    """Convert the persisted UTC call-start timestamp into tenant-local time."""
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    return started_at.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)


def customer_only_transcript(transcript: str | None) -> str:
    lines = []
    for line in (transcript or "").splitlines():
        if line.upper().startswith("CUSTOMER:"):
            lines.append(line.split(":", 1)[1].strip())
    return " ".join(lines)


def _matches_meridian(text: str, hour: int, minute: int) -> str | None:
    h12 = hour % 12 or 12
    time_pattern = rf"(?<!\d)0?{h12}(?::0?{minute:02d})?\s*(a\.?m\.?|p\.?m\.?)"
    match = re.search(time_pattern, text or "", re.I)
    if match:
        return "AM" if match.group(1).lower().startswith("a") else "PM"
    # Common explicit spoken equivalents; do not infer from assistant turns.
    phrase = rf"(?<!\d)0?{h12}(?::0?{minute:02d})?\s+(?:in the )?(morning|afternoon|evening|night)"
    match = re.search(phrase, text or "", re.I)
    if match:
        return "AM" if match.group(1).lower() == "morning" else "PM"
    return None


def _inside_hours(open_time: time, close_time: time, candidate: time) -> bool:
    if open_time <= close_time:
        return open_time <= candidate < close_time
    return candidate >= open_time or candidate < close_time


def resolve_voice_time(
    raw_time: str,
    customer_transcript: str | None,
    hours,
    appointment_date: date,
    call_local: datetime,
) -> dict:
    """Resolve an explicit, 24-hour, or ambiguous spoken time using tenant hours.

    Ambiguous 1..12 values resolve only when exactly one interpretation is
    inside business hours and is not already past at the call timestamp.
    Both/neither valid means the caller must clarify.
    """
    raw = (raw_time or "").strip().upper().replace(".", "")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)?", raw)
    if not match:
        return {"status": "invalid"}
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridian = match.group(3)
    if minute > 59 or hour > 23:
        return {"status": "invalid"}

    # 24-hour inputs 13..23 and 00 are unambiguous.
    if hour == 0 or hour > 12:
        resolved_hour = hour
        explicit = True
    elif meridian:
        # The model may attach a meridian the caller never spoke. Only trust it
        # when the customer transcript independently contains that marker.
        spoken = _matches_meridian(customer_only_transcript(customer_transcript), hour, minute)
        if spoken:
            resolved_hour = hour % 12 + (12 if spoken == "PM" else 0)
            explicit = True
        else:
            meridian = None
            explicit = False
    else:
        spoken = _matches_meridian(customer_only_transcript(customer_transcript), hour, minute)
        if spoken:
            resolved_hour = hour % 12 + (12 if spoken == "PM" else 0)
            explicit = True
        else:
            explicit = False

    if explicit:
        return {"status": "resolved", "time": time(resolved_hour, minute), "explicit": True}

    # A bare 12 means noon/midnight; evaluate both.
    candidates = [time(hour % 12, minute), time(hour % 12 + 12, minute)]
    valid = []
    for candidate in candidates:
        inside = bool(hours and not hours.is_closed and _inside_hours(
            hours.open_time, hours.close_time, candidate
        ))
        future = appointment_date > call_local.date() or (
            appointment_date == call_local.date()
            and datetime.combine(appointment_date, candidate) > call_local
        )
        if inside and future:
            valid.append(candidate)
    if len(valid) == 1:
        return {"status": "resolved", "time": valid[0], "explicit": False,
                "resolution": "unique_business_hours_and_call_time"}
    return {
        "status": "clarification_required",
        "candidates": [x.strftime("%H:%M") for x in candidates],
        "valid_candidates": [x.strftime("%H:%M") for x in valid],
    }
