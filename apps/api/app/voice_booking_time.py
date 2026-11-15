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
    return "\n".join(lines)


def _matches_meridian(text: str, hour: int, minute: int) -> str | None:
    h12 = hour % 12 or 12
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if lines:
        # A caller may answer a clarification with only "PM" or "I meant PM".
        # Apply that response to the already-established ambiguous time.
        standalone = re.fullmatch(
            r"(?:(?:i mean|i meant|make it|sorry|no|yes|please|in the)\s+)?(a\.?m\.?|p\.?m\.?|morning|afternoon|evening|night)",
            lines[-1], re.I
        )
        if standalone:
            value = standalone.group(1).lower()
            return "AM" if value.startswith("a") or value == "morning" else "PM"
    time_pattern = rf"(?<!\d)0?{h12}(?::0?{minute:02d})?\s*(a\.?m\.?|p\.?m\.?)"
    matches = list(re.finditer(time_pattern, text or "", re.I))
    if matches:
        # The latest customer correction wins (e.g. "9 AM — sorry, 9 PM").
        match = matches[-1]
        return "AM" if match.group(1).lower().startswith("a") else "PM"
    # Explicit spoken equivalents in English and common Indian languages.
    am_words = r"morning|subah|सुबह|ఉదయం|காலை|ಬೆಳಿಗ್ಗೆ|രാവിലെ|सकाळी|সকাল|સવારે|ਸਵੇਰੇ|صبح"
    pm_words = r"afternoon|evening|night|shaam|शाम|సాయంత్రం|రాత్రి|மாலை|இரவு|ಸಂಜೆ|ರಾತ್ರಿ|വൈകുന്നേരം|സന്ധ്യ|संध्याकाळी|সন্ধ্যা|রাত|સાંજે|ਸ਼ਾਮ|رات"
    phrase = rf"(?<!\d)0?{h12}(?::0?{minute:02d})?\s+(?:in the )?({am_words}|{pm_words})"
    matches = list(re.finditer(phrase, text or "", re.I))
    if matches:
        word = matches[-1].group(1).casefold()
        return "AM" if word in {"morning", "subah", "सुबह", "ఉదయం", "காலை", "ಬೆಳಿಗ್ಗೆ", "രാവിലെ", "सकाळी", "সকাল", "સવારે", "ਸਵੇਰੇ", "صبح"} else "PM"
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

    customer_text = customer_only_transcript(customer_transcript)
    h12 = hour % 12 or 12

    # Customer speech is authoritative. First honour an explicit meridian,
    # even if the realtime model serialized a conflicting 24-hour value.
    spoken = _matches_meridian(customer_text, h12, minute)
    spoken_24_hour = None
    for spoken_match in re.finditer(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", customer_text):
        spoken_hour = int(spoken_match.group(1))
        spoken_minute = int(spoken_match.group(2))
        if spoken_minute == minute and spoken_hour in (0, *range(13, 24)) and (spoken_hour % 12 or 12) == h12:
            spoken_24_hour = spoken_hour
    if spoken:
        resolved_hour = h12 % 12 + (12 if spoken == "PM" else 0)
        explicit = True
    elif spoken_24_hour is not None:
        resolved_hour = spoken_24_hour
        explicit = True
    else:
        # Trust 24-hour notation only when the customer actually said that
        # exact 24-hour value. A model-produced 17:30 for a bare "5:30" is
        # still ambiguous and must go through the two-candidate decision.
        exact_24h = False
        if hour == 0 or hour > 12:
            raw_24 = f"{hour:02d}:{minute:02d}"
            exact_24h = bool(re.search(
                rf"(?<!\\d){re.escape(raw_24)}(?!\\d)", customer_text
            ))
        if exact_24h:
            resolved_hour = hour
            explicit = True
        else:
            resolved_hour = h12 % 12
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
