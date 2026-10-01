"""Business hours handler.

Universal for all industries. Reads the tenant's BusinessHour rows and answers
time/date/day-aware questions in 11 languages.

Sub-intents handled:
1. full          - "what are your hours"
2. today         - "are you open today"
3. now           - "are you open now"
4. next_open     - "when do you open"
5. next_close    - "when do you close"
6. closed_today  - "are you closed today"
7. default       - anything else mentioning hours
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, time as dtime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Multi-language message templates.
# Keys are format markers; values are per-language strings.
# ---------------------------------------------------------------------------

_MSG = {
    "en": {
        "not_configured": "I'll have the team confirm our hours and get back to you.",
        "open_until": "Yes, we're open. We close at {time}.",
        "open_until_soon": "We're still open, but we close soon at {time}.",
        "opening_soon": "We open in about {mins} minutes at {time}.",
        "closed_now_opens_later_today": "We're closed right now. We open at {time} today.",
        "closed_now_opens_tomorrow": "We're closed right now. We open {day} at {time}.",
        "closed_today_opens_next": "We're closed today. We open {day} at {time}.",
        "open_today_until": "Yes, today ({day}) we're open until {time}.",
        "today_hours": "Today ({day}) we're open from {open} to {close}.",
        "today_hours_split": "Today ({day}) we're open {shifts}.",
        "today_closed": "We're closed today ({day}).",
        "next_open_today": "We open today at {time}.",
        "next_open_tomorrow": "We open tomorrow ({day}) at {time}.",
        "next_open_day": "We open on {day} at {time}.",
        "next_close_today": "We close today at {time}.",
        "next_close_tomorrow": "We close tomorrow at {time}.",
        "next_close_day": "We close on {day} at {time}.",
        "already_open_today": "We're already open. We close at {time}.",
        "already_closed_today": "We've already closed for today. We open {day} at {time}.",
        "full_week_summary": "We're open {summary}.",
        "full_week_list": "Our hours are: {list}.",
        "open_247": "We're open 24 hours, every day.",
        "closed_all_week": "We're closed all week.",
        "day_names": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "day_short": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "and": "and",
        "till": "to",
    },
    "hi": {
        "not_configured": "मैं टीम से पुष्टि करके आपको बताऊंगी।",
        "open_until": "हाँ, हम खुले हैं। हम {time} बजे बंद होते हैं।",
        "open_until_soon": "हम अभी खुले हैं, लेकिन {time} बजे बंद हो जाएंगे।",
        "opening_soon": "हम लगभग {mins} मिनट में {time} बजे खुलेंगे।",
        "closed_now_opens_later_today": "हम अभी बंद हैं। हम आज {time} बजे खुलेंगे।",
        "closed_now_opens_tomorrow": "हम अभी बंद हैं। हम {day} को {time} बजे खुलेंगे।",
        "closed_today_opens_next": "हम आज बंद हैं। हम {day} को {time} बजे खुलेंगे।",
        "open_today_until": "हाँ, आज ({day}) हम {time} बजे तक खुले हैं।",
        "today_hours": "आज ({day}) हम {open} से {close} तक खुले हैं।",
        "today_hours_split": "आज ({day}) हम {shifts} खुले हैं।",
        "today_closed": "आज ({day}) हम बंद हैं।",
        "next_open_today": "हम आज {time} बजे खुलेंगे।",
        "next_open_tomorrow": "हम कल ({day}) {time} बजे खुलेंगे।",
        "next_open_day": "हम {day} को {time} बजे खुलेंगे।",
        "next_close_today": "हम आज {time} बजे बंद होंगे।",
        "next_close_tomorrow": "हम कल {time} बजे बंद होंगे।",
        "next_close_day": "हम {day} को {time} बजे बंद होंगे।",
        "already_open_today": "हम पहले से खुले हैं। हम {time} बजे बंद होंगे।",
        "already_closed_today": "हम आज के लिए बंद हो चुके हैं। हम {day} को {time} बजे खुलेंगे।",
        "full_week_summary": "हम {summary} खुले रहते हैं।",
        "full_week_list": "हमारे समय: {list}।",
        "open_247": "हम चौबीसों घंटे खुले रहते हैं।",
        "closed_all_week": "हम पूरे सप्ताह बंद हैं।",
        "day_names": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
        "day_short": ["सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"],
        "and": "और",
        "till": "से",
    },
    "te": {
        "not_configured": "నేను బృందంతో నిర్ధారించి మీకు తెలియజేస్తాను.",
        "open_until": "అవును, మేము తెరిచి ఉన్నాము. {time}కి మూస్తాము.",
        "open_until_soon": "మేము ఇంకా తెరిచి ఉన్నాము, కానీ {time}కి మూస్తాము.",
        "opening_soon": "మేము సుమారు {mins} నిమిషాల్లో {time}కి తెరుస్తాము.",
        "closed_now_opens_later_today": "మేము ఇప్పుడు మూసి ఉన్నాము. ఈరోజు {time}కి తెరుస్తాము.",
        "closed_now_opens_tomorrow": "మేము ఇప్పుడు మూసి ఉన్నాము. {day} {time}కి తెరుస్తాము.",
        "closed_today_opens_next": "ఈరోజు మేము మూసి ఉన్నాము. {day} {time}కి తెరుస్తాము.",
        "open_today_until": "అవును, ఈరోజు ({day}) {time} వరకు తెరిచి ఉన్నాము.",
        "today_hours": "ఈరోజు ({day}) {open} నుండి {close} వరకు తెరిచి ఉన్నాము.",
        "today_hours_split": "ఈరోజు ({day}) {shifts} తెరిచి ఉన్నాము.",
        "today_closed": "ఈరోజు ({day}) మేము మూసి ఉన్నాము.",
        "next_open_today": "ఈరోజు {time}కి తెరుస్తాము.",
        "next_open_tomorrow": "రేపు ({day}) {time}కి తెరుస్తాము.",
        "next_open_day": "{day} {time}కి తెరుస్తాము.",
        "next_close_today": "ఈరోజు {time}కి మూస్తాము.",
        "next_close_tomorrow": "రేపు {time}కి మూస్తాము.",
        "next_close_day": "{day} {time}కి మూస్తాము.",
        "already_open_today": "మేము ఇప్పటికే తెరిచి ఉన్నాము. {time}కి మూస్తాము.",
        "already_closed_today": "ఈరోజు మూసేశాము. {day} {time}కి తెరుస్తాము.",
        "full_week_summary": "మేము {summary} తెరిచి ఉంటాము.",
        "full_week_list": "మా సమయాలు: {list}.",
        "open_247": "మేము 24 గంటలు తెరిచి ఉంటాము.",
        "closed_all_week": "మేము వారం మొత్తం మూసి ఉన్నాము.",
        "day_names": ["సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం"],
        "day_short": ["సోమ", "మంగళ", "బుధ", "గురు", "శుక్ర", "శని", "ఆది"],
        "and": "మరియు",
        "till": "నుండి",
    },
    "ta": {
        "not_configured": "குழுவுடன் உறுதிசெய்து உங்களுக்கு தெரிவிக்கிறேன்.",
        "open_until": "ஆம், நாங்கள் திறந்திருக்கிறோம். {time} மணிக்கு மூடுவோம்.",
        "open_until_soon": "நாங்கள் இன்னும் திறந்திருக்கிறோம், {time} மணிக்கு மூடுவோம்.",
        "opening_soon": "நாங்கள் சுமார் {mins} நிமிடங்களில் {time} மணிக்கு திறப்போம்.",
        "closed_now_opens_later_today": "இப்போது மூடியிருக்கிறோம். இன்று {time} மணிக்கு திறப்போம்.",
        "closed_now_opens_tomorrow": "இப்போது மூடியிருக்கிறோம். {day} அன்று {time} மணிக்கு திறப்போம்.",
        "closed_today_opens_next": "இன்று மூடியிருக்கிறோம். {day} அன்று {time} மணிக்கு திறப்போம்.",
        "open_today_until": "ஆம், இன்று ({day}) {time} வரை திறந்திருக்கிறோம்.",
        "today_hours": "இன்று ({day}) {open} முதல் {close} வரை திறந்திருக்கிறோம்.",
        "today_hours_split": "இன்று ({day}) {shifts} திறந்திருக்கிறோம்.",
        "today_closed": "இன்று ({day}) மூடியிருக்கிறோம்.",
        "next_open_today": "இன்று {time} மணிக்கு திறப்போம்.",
        "next_open_tomorrow": "நாளை ({day}) {time} மணிக்கு திறப்போம்.",
        "next_open_day": "{day} அன்று {time} மணிக்கு திறப்போம்.",
        "next_close_today": "இன்று {time} மணிக்கு மூடுவோம்.",
        "next_close_tomorrow": "நாளை {time} மணிக்கு மூடுவோம்.",
        "next_close_day": "{day} அன்று {time} மணிக்கு மூடுவோம்.",
        "already_open_today": "நாங்கள் ஏற்கனவே திறந்திருக்கிறோம். {time} மணிக்கு மூடுவோம்.",
        "already_closed_today": "இன்றைய திறப்பு முடிந்தது. {day} அன்று {time} மணிக்கு திறப்போம்.",
        "full_week_summary": "நாங்கள் {summary} திறந்திருக்கிறோம்.",
        "full_week_list": "எங்கள் நேரங்கள்: {list}.",
        "open_247": "நாங்கள் 24 மணி நேரமும் திறந்திருக்கிறோம்.",
        "closed_all_week": "வாரம் முழுவதும் மூடியிருக்கிறோம்.",
        "day_names": ["திங்கள்", "செவ்வாய்", "புதன்", "வியாழன்", "வெள்ளி", "சனி", "ஞாயிறு"],
        "day_short": ["திங்", "செவ்", "புத", "வியா", "வெள்", "சனி", "ஞாயி"],
        "and": "மற்றும்",
        "till": "முதல்",
    },
}

# Fallback to English for languages not yet translated
_SUPPORTED_LANGS = list(_MSG.keys())


def _msg(lang: str, key: str, **kwargs) -> str:
    """Get a message in the given language, with format variables applied.

    Only informational messages are here. Gendered receptionist messages
    (not_configured, checking_with_team, etc.) are resolved via AgentVoice.
    """
    lang_msgs = _MSG.get(lang) or _MSG["en"]
    template = lang_msgs.get(key) or _MSG["en"].get(key, "")
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


def _msg_gendered(lang: str, context: dict, key: str, **kwargs) -> str:
    """Resolve a gendered message via AgentVoice, with local fallback."""
    try:
        from .agent_voice import AgentVoice
        gender = (context or {}).get("agent_gender", "female")
        voice = AgentVoice(language=lang or "en", gender=gender)
        return voice.render(key, **kwargs)
    except Exception:
        return _msg(lang, key, **kwargs)


# ---------------------------------------------------------------------------
# Sub-intent detection
# ---------------------------------------------------------------------------

# === CLASSIFIER-BASED SUB-INTENT DETECTION ===
_SUBINTENT_MAP = {
    "business_hours_full":         "full",
    "business_hours_today":        "today",
    "business_hours_now":          "now",
    "business_hours_next_open":    "next_open",
    "business_hours_next_close":   "next_close",
    "business_hours_closed_today": "closed_today",
    "business_hours":              "default",
}


def detect_hours_subintent(message: str, language: str = "en") -> str:
    """Detect which hours-related question the customer is asking.

    Uses the shared multilingual classifier. All 11 languages are supported
    via intent_patterns.py; no per-language patterns live in this file.
    """
    try:
        from .intent_classifier import classify
    except Exception:
        return "default"
    try:
        result = classify(message or "", language)
        return _SUBINTENT_MAP.get(result.intent, "default")
    except Exception:
        return "default"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_hours(db: Session, tenant) -> dict:
    """Load all BusinessHour rows for the tenant, grouped by weekday.

    Returns: {0: [shift, shift, ...], 1: [...], ..., 6: [...]}
    A shift is a dict: {"open": time, "close": time, "interval": int}
    Closed days are weekday keys that have a single "closed" shift.
    """
    try:
        from .models_growth import BusinessHour
        rows = db.scalars(
            select(BusinessHour)
            .where(BusinessHour.tenant_id == tenant.id)
            .order_by(BusinessHour.weekday, BusinessHour.open_time)
        ).all()
    except Exception as exc:
        logger.debug("BusinessHour load failed: %s", exc)
        return {}

    grouped: dict = {i: [] for i in range(7)}
    for r in rows:
        grouped[r.weekday].append({
            "open": r.open_time,
            "close": r.close_time,
            "interval": r.slot_interval_minutes or 30,
            "is_closed": bool(r.is_closed),
        })
    return grouped


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _now_local(tenant) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(getattr(tenant, "timezone", "Asia/Kolkata") or "Asia/Kolkata")
        return datetime.now(tz)
    except Exception:
        return datetime.utcnow()


def _shift_active(shift: dict, now_t: dtime) -> bool:
    """Is the given shift covering the given local time (today)?"""
    if shift.get("is_closed"):
        return False
    op, cl = shift["open"], shift["close"]
    if op == cl:
        # 24-hour convention
        return True
    if op < cl:
        # Normal shift
        return op <= now_t < cl
    # Overnight: op > cl, spans midnight. Active if now >= op OR now < cl
    return now_t >= op or now_t < cl


def _is_open_now(grouped: dict, now: datetime) -> Optional[dict]:
    """Return info about the current open state.

    Returns:
      {
        "open": True/False,
        "closes_at": time or None (if open),
        "opens_at": time or None (if closed but opens later today),
        "next_day": weekday int or None (if closed today entirely),
      }
    """
    today = now.weekday()
    now_t = now.time()
    todays_shifts = grouped.get(today, [])

    # Check if any shift today (or yesterday's overnight) covers now.
    active = None
    for s in todays_shifts:
        if _shift_active(s, now_t):
            active = s
            break

    # Also check yesterday's overnight shifts (which extend into today).
    if not active:
        yesterday = (today - 1) % 7
        for s in grouped.get(yesterday, []):
            if s.get("is_closed"):
                continue
            if s["open"] > s["close"] and now_t < s["close"]:
                # Overnight from yesterday still active
                active = s
                break

    if active:
        return {"open": True, "closes_at": active["close"]}

    # Closed. When does it open next? Today later, or a future day.
    for s in todays_shifts:
        if s.get("is_closed"):
            continue
        if s["open"] > now_t:
            return {"open": False, "opens_at": s["open"], "same_day": True}

    # No more shifts today. Find next open day.
    for offset in range(1, 8):
        day = (today + offset) % 7
        for s in grouped.get(day, []):
            if s.get("is_closed"):
                continue
            return {"open": False, "opens_at": s["open"], "same_day": False, "next_day": day}
    return {"open": False, "opens_at": None, "same_day": False}


# ---------------------------------------------------------------------------
# Format helpers
# ---------------------------------------------------------------------------

def _fmt_time(t, style: str = "ampm") -> str:
    if t is None:
        return ""
    if style == "24h":
        return t.strftime("%H:%M")
    return t.strftime("%I:%M %p").lstrip("0")


def _detect_time_style(message: str) -> str:
    """Match the customer's time format. Default is AM/PM."""
    m = message or ""
    if re.search(r"\b\d{1,2}:\d{2}\b", m):
        return "24h"
    if re.search(r"\b(am|pm|a\.m\.|p\.m\.)\b", m, re.IGNORECASE):
        return "ampm"
    return "ampm"


def _day_name(weekday: int, lang: str, short: bool = False) -> str:
    key = "day_short" if short else "day_names"
    names = _MSG.get(lang, _MSG["en"]).get(key, _MSG["en"][key])
    if 0 <= weekday < len(names):
        return names[weekday]
    return str(weekday)


# ---------------------------------------------------------------------------
# Format handlers for each sub-intent
# ---------------------------------------------------------------------------

def _format_full_week(grouped: dict, style: str, lang: str) -> str:
    """Full weekly summary, auto-summarized where possible."""
    if not any(grouped.get(d) for d in range(7)):
        return _msg(lang, "not_configured")

    # Check if all 7 days have the same hours (and only one shift per day)
    same_all = True
    reference = None
    for d in range(7):
        shifts = [s for s in grouped[d] if not s.get("is_closed")]
        if len(shifts) != 1:
            same_all = False
            break
        s = shifts[0]
        sig = (s["open"], s["close"])
        if reference is None:
            reference = sig
        elif sig != reference:
            same_all = False
            break
    if same_all and reference:
        op, cl = reference
        if op == cl:
            return _msg(lang, "open_247")
        return _msg(lang, "full_week_summary", summary=f"{_fmt_time(op, style)} {_msg(lang,'till')} {_fmt_time(cl, style)}, 7 days a week")

    # Check if Mon-Sat same, Sunday closed (or vice versa)
    def sig(day_list):
        s = []
        for d in day_list:
            shifts = [x for x in grouped[d] if not x.get("is_closed")]
            s.append(tuple((x["open"], x["close"]) for x in shifts))
        return tuple(s)

    weekday_sig = sig([0, 1, 2, 3, 4, 5])
    sunday_shifts = [x for x in grouped[6] if not x.get("is_closed")]
    if weekday_sig and len(set(weekday_sig)) == 1 and len(weekday_sig[0]) == 1 and not sunday_shifts:
        op, cl = weekday_sig[0][0]
        summary = f"{_day_name(0, lang, True)}-{_day_name(5, lang, True)} {_fmt_time(op, style)} {_msg(lang,'till')} {_fmt_time(cl, style)}, {_day_name(6, lang)} closed"
        return _msg(lang, "full_week_summary", summary=summary)

    # Fallback: list per day
    lines = []
    for d in range(7):
        shifts = grouped.get(d, [])
        if not shifts or all(s.get("is_closed") for s in shifts):
            lines.append(f"{_day_name(d, lang, True)}: closed")
            continue
        parts = [f"{_fmt_time(s['open'], style)}-{_fmt_time(s['close'], style)}" for s in shifts if not s.get("is_closed")]
        lines.append(f"{_day_name(d, lang, True)}: {', '.join(parts)}")
    return _msg(lang, "full_week_list", list="; ".join(lines))


def _format_today(grouped: dict, now: datetime, style: str, lang: str) -> str:
    """Today's hours + status (leads with status)."""
    today = now.weekday()
    shifts = [s for s in grouped.get(today, []) if not s.get("is_closed")]

    if not shifts:
        # Today is closed entirely.
        state = _is_open_now(grouped, now)
        if state.get("next_day") is not None:
            return _msg(lang, "closed_today_opens_next",
                        day=_day_name(state["next_day"], lang),
                        time=_fmt_time(state.get("opens_at"), style))
        return _msg(lang, "today_closed", day=_day_name(today, lang))

    state = _is_open_now(grouped, now)
    if state.get("open"):
        return _msg(lang, "open_today_until",
                    day=_day_name(today, lang),
                    time=_fmt_time(state.get("closes_at"), style))

    # Closed right now but opens today.
    if state.get("same_day") and state.get("opens_at"):
        return _msg(lang, "closed_now_opens_later_today",
                    time=_fmt_time(state["opens_at"], style))

    # Closed, opens a future day.
    if state.get("next_day") is not None:
        return _msg(lang, "closed_now_opens_tomorrow" if (state["next_day"] - today) % 7 == 1 else "closed_today_opens_next",
                    day=_day_name(state["next_day"], lang),
                    time=_fmt_time(state.get("opens_at"), style))

    # Fallback: list today's shifts.
    if len(shifts) == 1:
        return _msg(lang, "today_hours",
                    day=_day_name(today, lang),
                    open=_fmt_time(shifts[0]["open"], style),
                    close=_fmt_time(shifts[0]["close"], style))
    parts = [f"{_fmt_time(s['open'], style)} {_msg(lang,'till')} {_fmt_time(s['close'], style)}" for s in shifts]
    return _msg(lang, "today_hours_split",
                day=_day_name(today, lang),
                shifts=f" {_msg(lang,'and')} ".join(parts))


def _format_now(grouped: dict, now: datetime, style: str, lang: str, threshold_min: int) -> str:
    """Time-aware status: open now / closed now + next state."""
    state = _is_open_now(grouped, now)
    today = now.weekday()

    if state.get("open"):
        closes = state.get("closes_at")
        if closes is not None and threshold_min > 0:
            # Compute minutes until close
            now_dt = datetime.combine(now.date(), now.time())
            close_dt = datetime.combine(now.date(), closes)
            if close_dt < now_dt:
                close_dt += timedelta(days=1)
            minutes_left = int((close_dt - now_dt).total_seconds() / 60)
            if 0 < minutes_left <= threshold_min:
                return _msg(lang, "open_until_soon", time=_fmt_time(closes, style))
        return _msg(lang, "open_until", time=_fmt_time(closes, style))

    # Closed now.
    opens_at = state.get("opens_at")
    if opens_at is not None and state.get("same_day"):
        # Opens later today.
        return _msg(lang, "closed_now_opens_later_today", time=_fmt_time(opens_at, style))

    if opens_at is not None and state.get("next_day") is not None:
        days_ahead = (state["next_day"] - today) % 7
        if days_ahead == 1:
            return _msg(lang, "closed_now_opens_tomorrow",
                        day=_day_name(state["next_day"], lang),
                        time=_fmt_time(opens_at, style))
        return _msg(lang, "closed_now_opens_tomorrow",
                    day=_day_name(state["next_day"], lang),
                    time=_fmt_time(opens_at, style))

    return _msg(lang, "not_configured")


def _format_next_open(grouped: dict, now: datetime, style: str, lang: str) -> str:
    """When does the tenant next open?"""
    state = _is_open_now(grouped, now)
    today = now.weekday()

    if state.get("open"):
        return _msg(lang, "already_open_today", time=_fmt_time(state.get("closes_at"), style))

    opens_at = state.get("opens_at")
    if opens_at is None:
        return _msg(lang, "not_configured")

    if state.get("same_day"):
        return _msg(lang, "next_open_today", time=_fmt_time(opens_at, style))

    next_day = state.get("next_day")
    days_ahead = (next_day - today) % 7 if next_day is not None else 0
    if days_ahead == 1:
        return _msg(lang, "next_open_tomorrow",
                    day=_day_name(next_day, lang),
                    time=_fmt_time(opens_at, style))
    return _msg(lang, "next_open_day",
                day=_day_name(next_day, lang),
                time=_fmt_time(opens_at, style))


def _format_next_close(grouped: dict, now: datetime, style: str, lang: str) -> str:
    """When does the tenant next close?"""
    state = _is_open_now(grouped, now)
    if state.get("open"):
        return _msg(lang, "next_close_today", time=_fmt_time(state.get("closes_at"), style))

    # Closed now. Find the next close (which is the close of the next open shift).
    today = now.weekday()
    opens_at = state.get("opens_at")
    next_day = state.get("next_day")

    if opens_at is not None:
        # Find the shift that starts at opens_at on that day
        target_day = today if state.get("same_day") else next_day
        for s in grouped.get(target_day, []):
            if s.get("is_closed"):
                continue
            if s["open"] == opens_at:
                days_ahead = (target_day - today) % 7
                if days_ahead == 1:
                    return _msg(lang, "next_close_tomorrow", time=_fmt_time(s["close"], style))
                return _msg(lang, "next_close_day",
                            day=_day_name(target_day, lang),
                            time=_fmt_time(s["close"], style))

    return _msg(lang, "not_configured")


def _format_closed_today(grouped: dict, now: datetime, style: str, lang: str) -> str:
    """Are we closed today? Time-aware."""
    state = _is_open_now(grouped, now)
    today = now.weekday()

    if state.get("open"):
        # Not closed, we're open. Warn if closing soon.
        closes = state.get("closes_at")
        now_dt = datetime.combine(now.date(), now.time())
        close_dt = datetime.combine(now.date(), closes) if closes else None
        if close_dt and close_dt < now_dt:
            close_dt += timedelta(days=1)
        minutes_left = int((close_dt - now_dt).total_seconds() / 60) if close_dt else None
        if minutes_left is not None and 0 < minutes_left <= 30:
            return _msg(lang, "open_until_soon", time=_fmt_time(closes, style))
        return _msg(lang, "open_until", time=_fmt_time(closes, style))

    # Closed now.
    opens_at = state.get("opens_at")
    if opens_at and state.get("same_day"):
        return _msg(lang, "closed_now_opens_later_today", time=_fmt_time(opens_at, style))

    if opens_at and state.get("next_day") is not None:
        return _msg(lang, "already_closed_today",
                    day=_day_name(state["next_day"], lang),
                    time=_fmt_time(opens_at, style))

    return _msg(lang, "today_closed", day=_day_name(today, lang))


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

async def handle_business_hours(
    db: Session,
    tenant,
    message: str,
    language: str,
    entities: dict,
    context: dict,
) -> Optional[str]:
    """Universal business-hours handler for all industries.

    Detects the sub-intent, loads the tenant's hours, and returns a
    time/date/day-aware reply in the customer's language.
    """
    try:
        grouped = _load_hours(db, tenant)
        if not grouped or not any(grouped.get(d) for d in range(7)):
            return _msg_gendered(language, context, "not_configured")

        subintent = detect_hours_subintent(message, language)
        style = _detect_time_style(message)
        now = _now_local(tenant)

        # Threshold: read from tenant config, default 30 min
        threshold = getattr(tenant, "closing_soon_minutes", 30) or 0
        if threshold not in (0, 15, 30):
            threshold = 30

        if subintent == "full":
            return _format_full_week(grouped, style, language)
        if subintent == "today":
            return _format_today(grouped, now, style, language)
        if subintent == "now":
            return _format_now(grouped, now, style, language, threshold)
        if subintent == "next_open":
            return _format_next_open(grouped, now, style, language)
        if subintent == "next_close":
            return _format_next_close(grouped, now, style, language)
        if subintent == "closed_today":
            return _format_closed_today(grouped, now, style, language)

        # Default: full weekly summary
        return _format_full_week(grouped, style, language)
    except Exception as exc:
        logger.exception("handle_business_hours failed: %s", exc)
        return _msg_gendered(language, context, "not_configured")