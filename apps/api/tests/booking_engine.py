"""Scenario engine for the booking conversation.

A scenario is a scripted phone call (a list of caller turns) with expectations about what the agent says and what ends
up in the database. Calls go through the REAL public endpoints (/call and /voice/turn) of the FastAPI app, so
confirmation, cancellation, rescheduling and conflict handling are exercised exactly as in production. A fresh tenant is
seeded for every scenario, no AI provider is configured (so nothing can spend tokens) and nothing touches the network.

Every tenant gets this behaviour by default: scenarios run on the default profile, and the "smoke" scenarios also run on
every other profile (other industries, time zones, opening hours, weekly closures).

Used by:
  tests/test_booking_scenarios.py   one pytest case per scenario (and per profile for the smoke set)
  qa/booking_script.py              writes docs/BOOKING_CALL_SCRIPT.md from the real transcripts
"""
from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CONFIRM_Q = "shall i confirm"
CONFIRMED = "your appointment is confirmed"
ASK_TIME = "what time would you prefer"
ASK_DAY_TIME = "which day and time would you prefer"


# ------------------------------------------------------------------------------------------------ tenant profiles

@dataclass(frozen=True)
class Profile:
    name: str
    industry: str
    tz: str
    open_t: tuple
    close_t: tuple
    closed: tuple          # weekdays closed (0=Monday ... 6=Sunday)


DEFAULT = Profile("dental-ist", "dental", "Asia/Kolkata", (9, 0), (18, 0), (6,))
PROFILES = [
    DEFAULT,
    Profile("restaurant-open-daily", "restaurant", "Asia/Kolkata", (11, 0), (23, 0), ()),
    Profile("salon-dubai-closed-friday", "salon", "Asia/Dubai", (10, 0), (20, 0), (4,)),
    Profile("clinic-new-york", "health", "America/New_York", (9, 0), (17, 0), (5, 6)),
    Profile("school-london-weekdays", "education", "Europe/London", (8, 0), (16, 0), (5, 6)),
    Profile("gym-sydney", "gym", "Australia/Sydney", (6, 0), (21, 0), (6,)),
]


# ------------------------------------------------------------------------------------------------ dates

class Dates(dict):
    """Placeholders usable in scenario text: {open_a} -> "Tuesday", {iso_a} -> "2026-10-20", {long_a} -> "Tuesday, October 20".

    open_a/open_b/open_c are the next OPEN weekdays at least two days ahead (in the tenant's own time zone, skipping its
    closed days), so a scenario never depends on the day it runs. {closed}/{iso_closed}/{long_closed} describe the next
    closed weekday of the profile (when it has one).
    """

    def __init__(self, profile: Profile = DEFAULT):
        super().__init__()
        from app.voice_followups import WEEKDAYS_HI, WEEKDAYS_TE
        now = datetime.now(ZoneInfo(profile.tz))
        self["today_name"] = WEEKDAYS[now.weekday()]
        self["tomorrow_name"] = WEEKDAYS[(now + timedelta(days=1)).weekday()]
        self["yesterday_name"] = WEEKDAYS[(now - timedelta(days=1)).weekday()]
        open_days = [(now + timedelta(days=o)).date() for o in range(2, 14) if (now + timedelta(days=o)).weekday() not in profile.closed]
        for key, d in zip("abcd", open_days):
            self[f"open_{key}"] = WEEKDAYS[d.weekday()]
            self[f"iso_{key}"] = d.isoformat()
            self[f"long_{key}"] = d.strftime("%A, %B %-d")
            self[f"dom_{key}"] = d.day
            self[f"mon_{key}"] = d.strftime("%B")
            self[f"slash_{key}"] = f"{d.day}/{d.month}"
            suffix = "th" if 10 <= d.day % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(d.day % 10, "th")
            self[f"ord_{key}"] = f"{d.day}{suffix}"
            self[f"hi_open_{key}"] = WEEKDAYS_HI[d.weekday()]
            self[f"te_open_{key}"] = WEEKDAYS_TE[d.weekday()]
        if profile.closed:
            first_closed = min(profile.closed)
            nxt = next((now + timedelta(days=o)).date() for o in range(2, 14) if (now + timedelta(days=o)).weekday() == first_closed)
            self["closed"] = WEEKDAYS[first_closed]
            self["iso_closed"] = nxt.isoformat()
            self["long_closed"] = nxt.strftime("%A, %B %-d")

    def __missing__(self, key):          # leave unknown {braces} alone
        return "{" + key + "}"

    def fmt(self, text):
        return text.format_map(self) if isinstance(text, str) else text


# ------------------------------------------------------------------------------------------------ spec

@dataclass
class T:
    """One caller turn and what must be true afterwards."""
    say: str
    who: str = "A"                       # which caller speaks ("A", "B": different people / phone numbers)
    has: list = field(default_factory=list)          # every substring must appear in the reply (case-insensitive)
    any_of: list = field(default_factory=list)       # at least one must appear
    not_has: list = field(default_factory=list)      # none may appear
    escalates: bool = False              # expected hand-off to a human/specialist (default: must NOT escalate)
    booking: dict = field(default_factory=dict)      # subset of response["booking"]
    action: str = ""                     # response["appointment_action"]["status"]
    db: dict = field(default_factory=dict)           # appointment counts by status for this tenant after the turn


@dataclass
class Scenario:
    id: str
    title: str
    category: str
    turns: list
    services: tuple = (("Consultation", 500, 30),)
    closed: tuple | None = None          # override the profile's closed weekdays; "tomorrow" closes tomorrow's weekday
    smoke: bool = False                  # also run on every other tenant profile
    needs_closed_day: bool = False       # only meaningful when the tenant has a weekly closed day
    xfail: str = ""                      # documented gap: reason (reported, not failed)


# ------------------------------------------------------------------------------------------------ runtime

class Harness:
    """Owns the FastAPI TestClient and the seeded database. Imported lazily so test collection never needs the app."""

    def __init__(self):
        from fastapi.testclient import TestClient
        from app import main
        from app.db import Base, SessionLocal, engine
        Base.metadata.create_all(engine)
        self.client = TestClient(main.app)
        self.SessionLocal = SessionLocal

    def seed(self, sc: Scenario, profile: Profile = DEFAULT):
        from app.models import Service, Tenant
        from app.models_growth import BusinessHour
        slug, tid = "scn-" + uuid.uuid4().hex[:10], str(uuid.uuid4())
        db = self.SessionLocal()
        db.add(Tenant(id=tid, name="Demo Clinic", slug=slug, industry=profile.industry, timezone=profile.tz))
        tomorrow_wd = (datetime.now(ZoneInfo(profile.tz)) + timedelta(days=1)).weekday()
        closed_spec = profile.closed if sc.closed is None else sc.closed
        closed = {tomorrow_wd if c == "tomorrow" else c for c in closed_spec}
        for wd in range(7):
            db.add(BusinessHour(tenant_id=tid, weekday=wd, open_time=time(*profile.open_t), close_time=time(*profile.close_t),
                                is_closed=wd in closed, slot_interval_minutes=30))
        for name, price, minutes in sc.services:
            db.add(Service(id=str(uuid.uuid4()), tenant_id=tid, name=name, price=price, currency="INR",
                           duration_minutes=minutes, is_active=True))
        db.commit()
        db.close()
        return slug, tid

    def appointment_counts(self, tid):
        from app.models_growth import Appointment
        db = self.SessionLocal()
        counts = {}
        for a in db.query(Appointment).filter(Appointment.tenant_id == tid).all():
            counts[a.status] = counts.get(a.status, 0) + 1
        db.close()
        return counts

    def start_call(self, slug, name, phone):
        r = self.client.post(f"/api/v1/public/business/{slug}/call", json={"name": name, "phone": phone})
        r.raise_for_status()
        return r.json()["call_id"]

    def turn(self, slug, call_id, conv, text):
        r = self.client.post(f"/api/v1/public/business/{slug}/voice/turn",
                             json={"transcript": text, "call_id": call_id, "conversation_id": conv, "channel": "voice"})
        assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:200]}"
        return r.json()


@dataclass
class Line:
    who: str
    said: str
    reply: str
    escalated: bool
    booking: dict
    action: str
    db: dict


class Mismatch(AssertionError):
    pass


def run_scenario(h: Harness, sc: Scenario, profile: Profile = DEFAULT, check: bool = True):
    """Play the scenario. Returns the transcript (list of Line). With check=True raises Mismatch on the first failure."""
    dates = Dates(profile)
    slug, tid = h.seed(sc, profile)
    callers: dict = {}
    transcript: list = []
    for number, t in enumerate(sc.turns, 1):
        if t.who not in callers:
            phone = "+91" + "9" + str(random.randint(100000000, 999999999))
            callers[t.who] = {"call": h.start_call(slug, f"Caller {t.who}", phone), "conv": None}
        c = callers[t.who]
        said = dates.fmt(t.say)
        data = h.turn(slug, c["call"], c["conv"], said)
        c["conv"] = data.get("conversation_id", c["conv"])
        reply = data.get("reply") or ""
        action = (data.get("appointment_action") or {}).get("status", "")
        line = Line(t.who, said, reply, bool(data.get("handoff_required")), data.get("booking") or {}, action,
                    h.appointment_counts(tid))
        transcript.append(line)
        if not check:
            continue
        where = f"[{sc.id} @ {profile.name}] turn {number} ({t.who}: {said!r}) -> {reply[:160]!r}"
        low = reply.casefold()
        if line.escalated != t.escalates:
            raise Mismatch(f"{where}\n  expected escalation={t.escalates}, got {line.escalated}")
        for s in t.has:
            if dates.fmt(s).casefold() not in low:
                raise Mismatch(f"{where}\n  reply is missing {dates.fmt(s)!r}")
        if t.any_of and not any(dates.fmt(s).casefold() in low for s in t.any_of):
            raise Mismatch(f"{where}\n  reply has none of {[dates.fmt(s) for s in t.any_of]}")
        for s in t.not_has:
            if dates.fmt(s).casefold() in low:
                raise Mismatch(f"{where}\n  reply must not contain {dates.fmt(s)!r}")
        for key, want in t.booking.items():
            got = line.booking.get(key)
            if str(got) != str(dates.fmt(want)) and not (isinstance(want, bool) and bool(got) == want):
                raise Mismatch(f"{where}\n  booking[{key!r}] expected {dates.fmt(want)!r}, got {got!r}")
        if t.action and line.action != t.action:
            raise Mismatch(f"{where}\n  appointment_action expected {t.action!r}, got {line.action!r}")
        for status, count in t.db.items():
            if line.db.get(status, 0) != count:
                raise Mismatch(f"{where}\n  appointments with status {status!r}: expected {count}, database has {line.db}")
    return transcript
