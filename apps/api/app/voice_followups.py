"""Deterministic answers for short spoken follow-ups. No AI model is ever called here.

Everything in this module is pure (no database, no network) so it can be unit-tested:

* ``spoken_time``      "9 30 am", "nine thirty", "half past nine", "ten o'clock"  ->  "9:30 AM" ...
* ``describe_day_hours``  "Tomorrow is Sunday, and we're closed. We reopen on Monday at 9:00 AM."
* ``is_day_followup``  "tomorrow", "and Sunday?", "what about Saturday"  (a bare day reference)

The brain uses these *inside* its existing stages (structured answer / booking entity extraction);
the order of the stages and the shape of the reply are unchanged.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from typing import Mapping, Optional

# --------------------------------------------------------------------------------------
# Spoken times
# --------------------------------------------------------------------------------------

_HOURS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}
_MINUTES = {"fifteen": 15, "twenty": 20, "thirty": 30, "fortyfive": 45, "fifty": 50}  # keys have no spaces/hyphens
_HOUR_WORD = "|".join(_HOURS)
_HOUR_ANY = rf"(?:1[0-2]|0?[1-9]|{_HOUR_WORD})"
_MIN_WORD = r"(?:fifteen|twenty|thirty|forty[\s-]?five|fifty)"
_CUE = r"(?:at|by|around|about|for|come|coming|reach|arrive|slot|time|appointment|book|booking|schedule|visit)"


def _to_hour(token: str) -> int:
    token = token.strip().lower()
    return _HOURS[token] if token in _HOURS else int(token)


def _meridiem(value: str, explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return "AM" if explicit.lower().startswith("a") else "PM"
    if re.search(r"\b(?:morning|subah|savere|uday|sakal)\b", value):
        return "AM"
    if re.search(r"\b(?:afternoon|evening|night|tonight|shaam|sanje)\b", value):
        return "PM"
    return None


def _fmt(hour: int, minute: int, mer: Optional[str]) -> str:
    base = f"{hour}:{minute:02d}" if minute else f"{hour}"
    return f"{base} {mer}" if mer else base


def spoken_time(text: str) -> Optional[str]:
    """Return a time string like "9:30 AM" / "9:30" / "10" from spoken-style English, else None.

    Deliberately conservative: it is only used when the original parser found no time, and every
    pattern needs a clear time signal (meridiem, "o'clock", "half/quarter past", or a time cue), so
    ordinary numbers in a sentence ("I have two kids") are not read as times.
    """
    v = (text or "").casefold().replace("a.m.", "am").replace("p.m.", "pm")
    v = re.sub(r"[,;!?]", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    if not v:
        return None

    # "half past nine" / "half past 9"
    m = re.search(rf"\bhalf (?:past|after) ({_HOUR_ANY})\b", v)
    if m:
        return _fmt(_to_hour(m.group(1)), 30, _meridiem(v))
    # "quarter past nine" / "quarter to ten"
    m = re.search(rf"\bquarter (?:past|after) ({_HOUR_ANY})\b", v)
    if m:
        return _fmt(_to_hour(m.group(1)), 15, _meridiem(v))
    m = re.search(rf"\bquarter to ({_HOUR_ANY})\b", v)
    if m:
        hour = _to_hour(m.group(1)) - 1 or 12
        return _fmt(hour, 45, _meridiem(v))

    # "ten o'clock" / "10 oclock" (digits are handled by the original parser; words are not)
    m = re.search(rf"\b({_HOUR_ANY}) o['’]?clock\b", v)
    if m:
        return _fmt(_to_hour(m.group(1)), 0, _meridiem(v))

    # "9 30 am", "9.30 pm", "9 30 a m"
    m = re.search(r"\b(1[0-2]|0?[1-9])[.\s]([0-5]\d)\s*(a\.?\s?m\.?|p\.?\s?m\.?)(?=\W|$)", v)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), _meridiem(v, m.group(3)))

    # "at 9 30" / "at 9.30" (no am/pm, but an explicit time cue)
    m = re.search(rf"\b{_CUE}\s+(1[0-2]|0?[1-9])[.\s]([0-5]\d)\b(?!\s*(?:am|pm|:))", v)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2)), _meridiem(v))

    # "nine thirty", "nine forty five", "nine fifteen am"
    m = re.search(rf"\b({_HOUR_WORD}) ({_MIN_WORD})(?![-\w])(?:\s*(am|pm))?\b", v)
    if m:
        minute = _MINUTES.get(re.sub(r"[\s-]+", "", m.group(2)))
        # quarter-hour minutes are unambiguous as a bare answer to "which time?"; 20/50 need a signal
        if minute is not None and (minute in (15, 30, 45) or m.group(3) or re.search(rf"\b{_CUE}\b", v) or _meridiem(v)):
            return _fmt(_to_hour(m.group(1)), minute, _meridiem(v, m.group(3)))
    return None


# --------------------------------------------------------------------------------------
# Answers to "What time would you prefer?"
# --------------------------------------------------------------------------------------

_ASKS_FOR_TIME = re.compile(r"\bwhat time\b|\bwhich time\b|\btime would you (?:prefer|like)\b", re.I)
_ASKS_FOR_DAY_TOO = re.compile(r"\b(?:day|date) and time\b", re.I)
_MIN_WORDS = {"five": 5, "ten": 10, "fifteen": 15, "twenty": 20, "twenty five": 25, "twenty-five": 25, "thirty": 30,
              "thirty five": 35, "thirty-five": 35, "forty": 40, "forty five": 45, "forty-five": 45, "fifty": 50,
              "fifty five": 55, "fifty-five": 55}
_MIN_ANY = "|".join(sorted((re.escape(k) for k in _MIN_WORDS), key=len, reverse=True))
_BARE_DIGITS = re.compile(
    r"^(?:at |around |about |by )?(1[0-2]|0?[1-9])(?:[\s.:\-]?([0-5]\d))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?(?: please| ok| okay| sir| madam)?$")
_BARE_WORDS = re.compile(
    rf"^(?:at |around |about |by )?({_HOUR_WORD})(?:[\s-]+({_MIN_ANY}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?(?: please| ok| okay| sir| madam)?$")


def asks_for_time(assistant_text: Optional[str]) -> bool:
    """True when the assistant's last message was a "What time would you prefer ...?" question."""
    if not assistant_text or _ASKS_FOR_DAY_TOO.search(assistant_text):
        return False   # "Which day and time ...?": a bare number could just as well be a date
    return bool(_ASKS_FOR_TIME.search(assistant_text))


def bare_time_answer(text: str) -> Optional[str]:
    """Turn a bare reply to "What time?" into a time: "10 10", "1010", "930", "10 30", "11", "ten ten".

    Speech recognition often drops the colon ("10:10" -> "10 10"). These shapes are only trusted
    when the assistant has just asked for a time (see asks_for_time); on their own they are just numbers.
    """
    v = re.sub(r"[,;!?]", " ", (text or "").casefold()).strip().rstrip(".")
    v = re.sub(r"\s+", " ", v)
    if not v:
        return None
    m = _BARE_DIGITS.match(v)
    if m:
        return _fmt(int(m.group(1)), int(m.group(2) or 0), _meridiem(v, m.group(3)))
    m = _BARE_WORDS.match(v)
    if m:
        minute = _MIN_WORDS.get(m.group(2), 0) if m.group(2) else 0
        return _fmt(_to_hour(m.group(1)), minute, _meridiem(v, m.group(3)))
    return None


# --------------------------------------------------------------------------------------
# Day-specific opening hours
# --------------------------------------------------------------------------------------

WEEKDAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAYS_HI = ("सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार")
WEEKDAYS_TE = ("సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం")
_WEEKDAYS = {"en": WEEKDAYS_EN, "hi": WEEKDAYS_HI, "te": WEEKDAYS_TE}
_REL = {
    "en": {"today": "Today", "tomorrow": "Tomorrow", "day_after_tomorrow": "The day after tomorrow"},
    "hi": {"today": "आज", "tomorrow": "कल", "day_after_tomorrow": "परसों"},
    "te": {"today": "ఈ రోజు", "tomorrow": "రేపు", "day_after_tomorrow": "ఎల్లుండి"},
}


def clock(t: time) -> str:
    """9:00 AM style, no leading zero."""
    return t.strftime("%I:%M %p").lstrip("0")


def _days(language: str):
    return _WEEKDAYS.get(language, WEEKDAYS_EN)


def next_open_day(hours: Mapping[int, object], after: date, horizon: int = 7):
    """First day after ``after`` (within a week) that has opening hours set and is not closed."""
    from datetime import timedelta
    for offset in range(1, horizon + 1):
        d = after + timedelta(days=offset)
        row = hours.get(d.weekday())
        if row is not None and not getattr(row, "is_closed", False):
            return d, row
    return None


def describe_day_hours(
    target: date,
    hours: Mapping[int, object],
    *,
    language: str = "en",
    relative: Optional[str] = None,
    now_local: Optional[datetime] = None,
    offer_booking: bool = False,
    closed_day_question: bool = False,
) -> Optional[str]:
    """One spoken sentence or two about whether the business is open on ``target``.

    ``hours`` maps weekday (0=Monday) to a row with ``is_closed``, ``open_time``, ``close_time``.
    Returns None when the tenant has no hours configured for that weekday (the caller then falls
    through to the normal ladder; nothing is ever guessed).
    """
    row = hours.get(target.weekday())
    if row is None:
        return None
    lang = language if language in _WEEKDAYS else "en"
    names = _days(lang)
    weekday = names[target.weekday()]
    rel = (relative or "").replace(" ", "_")
    rel_word = _REL[lang].get(rel)
    closed = bool(getattr(row, "is_closed", False))
    nxt = next_open_day(hours, target) if closed or (now_local and target == now_local.date()) else None

    if lang == "hi":
        lead = f"{rel_word} {weekday}" if rel_word else weekday
        if closed:
            text = (f"{lead} है और हम बंद रहते हैं।" if rel_word else f"{weekday} को हम बंद रहते हैं।")
            if nxt:
                text += f" हम {names[nxt[0].weekday()]} को {clock(nxt[1].open_time)} पर फिर खुलेंगे।"
            return text
        return f"{lead} को हम {clock(row.open_time)} से {clock(row.close_time)} तक खुले रहते हैं।"

    if lang == "te":
        lead = f"{rel_word} {weekday}" if rel_word else weekday
        if closed:
            text = f"{lead}, మేము మూసివేసి ఉంటాము."
            if nxt:
                text += f" {names[nxt[0].weekday()]} {clock(nxt[1].open_time)} కి తెరుస్తాము."
            return text
        return f"{lead} మేము {clock(row.open_time)} నుండి {clock(row.close_time)} వరకు తెరిచి ఉంటాము."

    # English (and the fallback for every other language)
    opening, closing = (clock(row.open_time), clock(row.close_time)) if not closed else ("", "")
    is_today = bool(now_local and target == now_local.date())
    if closed:
        text = f"{rel_word} is {weekday}, and we're closed." if rel_word else f"On {weekday} we're closed."
        if nxt:
            text += f" We reopen on {names[nxt[0].weekday()]} at {clock(nxt[1].open_time)}."
            if offer_booking:
                text += f" Would you like to book an appointment for {names[nxt[0].weekday()]}?"
            elif closed_day_question:
                text += " Which day would you prefer instead?"
        return text

    lead = f"{rel_word}, {weekday}," if rel_word else f"On {weekday},"
    if is_today and now_local.time() >= row.close_time:
        text = f"{lead} we were open from {opening} to {closing}, and we've closed for the day."
        if nxt:
            text += f" We reopen on {names[nxt[0].weekday()]} at {clock(nxt[1].open_time)}."
    elif is_today and now_local.time() < row.open_time:
        text = f"{lead} we open at {opening} and close at {closing}."
        if offer_booking:
            text += " Would you like to book an appointment?"
    else:
        text = f"{lead} we're open from {opening} to {closing}."
        if offer_booking:
            text += " Would you like to book an appointment?"
    return text


# --------------------------------------------------------------------------------------
# Plain refusals: "no", "no no", "nope", "nahi" ... meaning depends on what was just asked
# --------------------------------------------------------------------------------------

def _plain(text: str) -> str:
    """Casefold, drop punctuation/symbols (keeps Indic letters and vowel signs), squeeze spaces."""
    kept = "".join(ch for ch in (text or "").casefold() if not unicodedata.category(ch).startswith(("P", "S")))
    return re.sub(r"\s+", " ", kept).strip()


_NEG = r"(?:no|nope|nah|naa|nahi|nahin|nai|\u0928\u0939\u0940\u0902|\u0928\u0939\u0940|\u0928\u094b|\u0c32\u0c47\u0c26\u0c41|\u0c35\u0c26\u0c4d\u0c26\u0c41)"
_REFUSAL_RE = re.compile(rf"^(?:{_NEG}(?: {_NEG})*(?: (?:thanks|thank you|please|sir|madam|ji))?|not now|not right now|not really)$")
_DONE_RE = re.compile(
    r"^(?:nothing|nothing else|that is all|thats all|i am good|im good|all good|all set|bas|bas itna|bas itna hi|kuch nahi|kuch nahin"
    r"|\u0915\u0941\u091b \u0928\u0939\u0940\u0902|\u092c\u0938|\u092c\u0938 \u0907\u0924\u0928\u093e)$")
_OFFERED_MORE_HELP = re.compile(r"anything else|here to help|still there|need anything|how can i help", re.I)


def is_refusal(message: str) -> bool:
    """A bare "no": "no", "no no", "nope", "nahi", "no thanks", "not now" ..."""
    return bool(_REFUSAL_RE.match(_plain(message)))


def is_nothing_else(message: str) -> bool:
    """"nothing else", "that's all", "I'm good", "bas" ... or any bare refusal."""
    value = _plain(message)
    return bool(_REFUSAL_RE.match(value) or _DONE_RE.match(value))


def decline_kind(state: Optional[str], last_assistant: Optional[str], message: str) -> Optional[str]:
    """What a bare refusal means, decided by what the assistant had just said:

    "confirmation"  the caller declined "Shall I confirm that appointment?"
    "offer"         the caller declined "Would you like to book an appointment?"
    "nothing_else"  the caller has nothing more to ask after "...anything else..." / a finished call
    None            no special meaning: the normal ladder decides
    """
    refusal, done = is_refusal(message), is_nothing_else(message)
    if not done:
        return None
    last = (last_assistant or "").casefold()
    if refusal and state == "booking_confirmation":
        return "confirmation"
    if refusal and "book an appointment" in last:
        return "offer"
    if state in ("closed", "booking_confirmed") or _OFFERED_MORE_HELP.search(last):
        return "nothing_else"
    return None


_DECLINE_TEXT = {
    "en": {
        "confirmation": "No problem. I haven't booked anything. Which day and time would you prefer instead?",
        "offer": "No problem. Is there anything else I can help you with?",
        "nothing_else": "Alright, thank you for calling {name}. Have a great day!",
    },
    "hi": {
        "confirmation": "\u0915\u094b\u0908 \u092c\u093e\u0924 \u0928\u0939\u0940\u0902, \u092e\u0948\u0902\u0928\u0947 \u0905\u092d\u0940 \u0915\u0941\u091b \u092c\u0941\u0915 \u0928\u0939\u0940\u0902 \u0915\u093f\u092f\u093e \u0939\u0948\u0964 \u0906\u092a \u0915\u093f\u0938 \u0926\u093f\u0928 \u0914\u0930 \u0915\u093f\u0938 \u0938\u092e\u092f \u0906\u0928\u093e \u091a\u093e\u0939\u0947\u0902\u0917\u0947?",
        "offer": "\u0915\u094b\u0908 \u092c\u093e\u0924 \u0928\u0939\u0940\u0902\u0964 \u0915\u094d\u092f\u093e \u092e\u0948\u0902 \u0906\u092a\u0915\u0940 \u0914\u0930 \u0915\u094b\u0908 \u092e\u0926\u0926 \u0915\u0930 \u0938\u0915\u0924\u093e \u0939\u0942\u0901?",
        "nothing_else": "\u0920\u0940\u0915 \u0939\u0948, {name} \u0915\u094b \u0915\u0949\u0932 \u0915\u0930\u0928\u0947 \u0915\u0947 \u0932\u093f\u090f \u0927\u0928\u094d\u092f\u0935\u093e\u0926\u0964 \u0906\u092a\u0915\u093e \u0926\u093f\u0928 \u0936\u0941\u092d \u0939\u094b!",
    },
    "te": {
        "confirmation": "\u0c2a\u0c30\u0c4d\u0c35\u0c3e\u0c32\u0c47\u0c26\u0c41, \u0c28\u0c47\u0c28\u0c41 \u0c07\u0c02\u0c15\u0c3e \u0c0f\u0c26\u0c40 \u0c2c\u0c41\u0c15\u0c4d \u0c1a\u0c47\u0c2f\u0c32\u0c47\u0c26\u0c41. \u0c0f \u0c30\u0c4b\u0c1c\u0c41 \u0c2e\u0c30\u0c3f\u0c2f\u0c41 \u0c0f \u0c38\u0c2e\u0c2f\u0c02 \u0c15\u0c3e\u0c35\u0c3e\u0c32\u0c3f?",
        "offer": "\u0c2a\u0c30\u0c4d\u0c35\u0c3e\u0c32\u0c47\u0c26\u0c41. \u0c07\u0c02\u0c15\u0c47\u0c2e\u0c48\u0c28\u0c3e \u0c38\u0c39\u0c3e\u0c2f\u0c02 \u0c15\u0c3e\u0c35\u0c3e\u0c32\u0c3e?",
        "nothing_else": "\u0c38\u0c30\u0c47, {name} \u0c15\u0c41 \u0c15\u0c3e\u0c32\u0c4d \u0c1a\u0c47\u0c38\u0c3f\u0c28\u0c02\u0c26\u0c41\u0c15\u0c41 \u0c27\u0c28\u0c4d\u0c2f\u0c35\u0c3e\u0c26\u0c3e\u0c32\u0c41. \u0c2e\u0c40 \u0c30\u0c4b\u0c1c\u0c41 \u0c36\u0c41\u0c2d\u0c02\u0c17\u0c3e \u0c09\u0c02\u0c21\u0c3e\u0c32\u0c3f!",
    },
}


def decline_reply(kind: str, language: str, business_name: str) -> str:
    table = _DECLINE_TEXT.get(language, _DECLINE_TEXT["en"])
    return table[kind].format(name=business_name or "us")


# --------------------------------------------------------------------------------------
# What counts as a bare "day" follow-up
# --------------------------------------------------------------------------------------

_FILLER = {
    "and", "what", "about", "how", "then", "ok", "okay", "yeah", "yes", "yep", "sure", "hmm", "so", "the",
    "on", "for", "is", "it", "its", "it's", "same", "also", "too", "that", "day", "please", "only", "a",
    "at", "in", "um", "uh", "well", "now", "will", "you", "be", "are", "we", "open", "available", "tell",
    "me", "do", "does",
}
_DAYWORDS = {
    "today", "tomorrow", "tonight", "after", "monday", "tuesday", "wednesday", "thursday", "friday",
    "saturday", "sunday", "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
    "yesterday", "weekend",
}
HOURS_CUES = re.compile(r"\b(holiday|holidays|working|work|closed|close|closing|open|opening|hours|timing|timings|off)\b")


def is_day_followup(message: str) -> bool:
    """True for "tomorrow", "and Sunday?", "what about Saturday", "कल", "రేపు" ... (a bare day)."""
    text = (message or "").strip().casefold()
    if not text:
        return False
    words = re.findall(r"[\w'’]+", text, flags=re.UNICODE)
    if not words or len(words) > 6:
        return False
    if any(not w.isascii() for w in words):  # Hindi / Telugu / ...: short utterance that already has a day entity
        return len(words) <= 3
    leftover = [w for w in words if w not in _FILLER and w not in _DAYWORDS]
    return not leftover
