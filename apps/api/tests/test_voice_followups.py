"""Library-first voice brain: day follow-ups, spoken times, day corrections, confirm, precision.

No AI model is called anywhere in this file (no provider keys are configured, so an unanswerable
question escalates instead of generating). Dates are computed from "now" so the tests pass on any
day of the week.
"""
import asyncio
from datetime import datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import brain
from app.ai_router import knowledge_match
from app.db import Base
from app.models import Service, Tenant
from app.models_growth import BusinessHour, KnowledgeItem
from app.voice_followups import (
    WEEKDAYS_EN, WEEKDAYS_HI, WEEKDAYS_TE, asks_for_time, bare_time_answer, describe_day_hours,
    is_day_followup, spoken_time,
)

TZ = "Asia/Kolkata"


def _now():
    return datetime.now(ZoneInfo(TZ))


def _day(offset):
    return (_now() + timedelta(days=offset)).date()


def make_db(closed_offsets=(), library=True):
    """Every weekday open 9-18, except the weekdays of today+offset for offsets in closed_offsets."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Tenant(id="t1", name="Demo Realty", slug="demo", industry="real_estate", timezone=TZ))
    closed = {_day(o).weekday() for o in closed_offsets}
    for wd in range(7):
        db.add(BusinessHour(tenant_id="t1", weekday=wd, open_time=time(9, 0), close_time=time(18, 0),
                            is_closed=wd in closed, slot_interval_minutes=30))
    db.add(Service(id="s1", tenant_id="t1", name="Site visit", price=0, currency="INR",
                   duration_minutes=30, is_active=True))
    if library:
        db.add(KnowledgeItem(tenant_id="t1", title="Parking", language="en", is_active=True,
                             approval_status="approved",
                             content="Free parking is available for visitors in the basement."))
        db.add(KnowledgeItem(tenant_id="t1", title="Location", language="en", is_active=True,
                             approval_status="approved",
                             content="We are located at 12 Lake View Road, Hyderabad, next to the metro station."))
    db.commit()
    return db


class Convo:
    """One caller talking to the real brain."""

    def __init__(self, db):
        self.db, self.cid, self.last = db, None, None

    def say(self, text):
        self.last = asyncio.run(brain.generate_reply(self.db, "t1", text, self.cid, "voice"))
        self.cid = self.last.get("conversation_id") or self.cid
        return self.last

    @property
    def reply(self):
        return self.last["reply"]

    @property
    def escalated(self):
        return bool(self.last.get("handoff_required"))

    @property
    def state(self):
        return self.db.get(brain.Conversation, self.cid).state


# ---------------------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Monday 9 30 am please", "9:30 AM"),
    ("book me for Monday at nine thirty", "9:30"),
    ("nine thirty", "9:30"),
    ("half past nine", "9:30"),
    ("can I come on Monday morning at half past nine", "9:30 AM"),
    ("ten o'clock", "10"),
    ("quarter past ten in the evening", "10:15 PM"),
    ("quarter to ten", "9:45"),
    ("nine forty-five am", "9:45 AM"),
    ("9.30 pm", "9:30 PM"),
    ("at 9 30", "9:30"),
    ("twelve thirty pm", "12:30 PM"),
])
def test_spoken_times(text, expected):
    assert spoken_time(text) == expected


@pytest.mark.parametrize("text", [
    "I have two kids", "I have two thirty-year-old cars", "call me on 9 30 September",
    "my number is 98 30", "ten twenty people came", "what are your timings",
])
def test_ordinary_numbers_are_not_times(text):
    assert spoken_time(text) is None


def test_brain_entity_extraction_uses_spoken_times():
    assert brain.extract_booking_entities("Monday 9 30 am please")["time"] == "9:30 AM"
    assert brain.extract_booking_entities("half past nine on Monday")["time"] == "9:30"
    assert brain.extract_booking_entities("9:30")["time"] == "9:30"   # unchanged behaviour


@pytest.mark.parametrize("text,expected", [
    ("tomorrow", True), ("and Sunday?", True), ("what about Saturday", True), ("today", True),
    ("how about Monday please", True), ("कल", True), ("రేపు", True),
    ("book an appointment tomorrow", False), ("what is the price for the site visit", False),
])
def test_day_followup_detection(text, expected):
    assert is_day_followup(text) is expected


def _hours(closed=()):
    return {wd: SimpleNamespace(is_closed=wd in closed, open_time=time(9, 0), close_time=time(18, 0))
            for wd in range(7)}


def _dt(y, m, d, h, mi):
    return datetime(y, m, d, h, mi, tzinfo=ZoneInfo(TZ))


def test_describe_open_and_closed_days_in_english():
    sat, sun, mon = _dt(2026, 10, 10, 11, 0).date(), _dt(2026, 10, 11, 11, 0).date(), _dt(2026, 10, 12, 11, 0).date()
    hours = _hours(closed={6})
    now = _dt(2026, 10, 10, 11, 0)
    assert describe_day_hours(sat, hours, relative="today", now_local=now) == "Today, Saturday, we're open from 9:00 AM to 6:00 PM."
    assert describe_day_hours(sun, hours, relative="tomorrow", now_local=now) == \
        "Tomorrow is Sunday, and we're closed. We reopen on Monday at 9:00 AM."
    assert describe_day_hours(sun, hours, now_local=now) == "On Sunday we're closed. We reopen on Monday at 9:00 AM."
    assert describe_day_hours(mon, hours, now_local=now, offer_booking=True) == \
        "On Monday, we're open from 9:00 AM to 6:00 PM. Would you like to book an appointment?"
    assert describe_day_hours(sun, hours, relative="tomorrow", now_local=now, offer_booking=True).endswith(
        "Would you like to book an appointment for Monday?")
    assert describe_day_hours(sun, hours, relative="tomorrow", now_local=now, closed_day_question=True).endswith(
        "Which day would you prefer instead?")


def test_describe_today_before_and_after_hours():
    sat = _dt(2026, 10, 10, 8, 0).date()
    hours = _hours(closed={6})
    after = describe_day_hours(sat, hours, relative="today", now_local=_dt(2026, 10, 10, 19, 0))
    assert "we've closed for the day" in after and "We reopen on Monday at 9:00 AM." in after
    before = describe_day_hours(sat, hours, relative="today", now_local=_dt(2026, 10, 10, 7, 30))
    assert before == "Today, Saturday, we open at 9:00 AM and close at 6:00 PM."


def test_describe_hindi_telugu_and_unknown_hours():
    sun = _dt(2026, 10, 11, 11, 0).date()
    now = _dt(2026, 10, 10, 11, 0)
    hours = _hours(closed={6})
    hi = describe_day_hours(sun, hours, language="hi", relative="tomorrow", now_local=now)
    assert hi.startswith("कल रविवार") and "बंद" in hi and WEEKDAYS_HI[0] in hi
    te = describe_day_hours(sun, hours, language="te", relative="tomorrow", now_local=now)
    assert te.startswith("రేపు ఆదివారం") and WEEKDAYS_TE[0] in te
    assert describe_day_hours(sun, {}, now_local=now) is None          # nothing configured -> never guess
    assert describe_day_hours(sun, hours, language="fr", relative="tomorrow", now_local=now).startswith("Tomorrow is Sunday")


# ---------------------------------------------------------------------------------------
# the real call: "timings" ... "tomorrow" used to escalate to the paid specialist layer
# ---------------------------------------------------------------------------------------

def test_tomorrow_after_hours_is_answered_from_the_hours_table_not_escalated():
    caller = Convo(make_db(closed_offsets=(1,)))
    caller.say("Manoj timings")
    assert not caller.escalated
    caller.say("tomorrow")
    tomorrow = WEEKDAYS_EN[_day(1).weekday()]
    assert not caller.escalated
    assert caller.last["provider"] == "deterministic"
    assert caller.reply.startswith(f"Tomorrow is {tomorrow}, and we're closed. We reopen on")
    assert "book an appointment" in caller.reply


@pytest.mark.parametrize("follow_up", ["tomorrow", "and tomorrow?", "what about tomorrow", "are you working tomorrow",
                                       "is tomorrow a holiday", "are you open tomorrow"])
def test_day_follow_up_phrasings(follow_up):
    caller = Convo(make_db(closed_offsets=(1,)))
    caller.say("what are your timings")
    caller.say(follow_up)
    assert not caller.escalated
    assert WEEKDAYS_EN[_day(1).weekday()] in caller.reply


def test_follow_ups_chain_and_name_the_right_weekday():
    caller = Convo(make_db())
    caller.say("what are your timings")
    day_after = WEEKDAYS_EN[_day(2).weekday()]
    caller.say(f"and {day_after}")
    assert not caller.escalated and f"On {day_after}," in caller.reply
    caller.say("what about tomorrow")                      # context survives the first follow-up
    assert not caller.escalated and "Tomorrow," in caller.reply


def test_bare_day_without_any_hours_context_is_not_guessed_at():
    caller = Convo(make_db(library=False))
    caller.say("tomorrow")
    assert caller.escalated                                   # unchanged: honest hand-off, nothing invented


def test_hindi_follow_up_is_answered_in_hindi():
    caller = Convo(make_db(closed_offsets=(1,)))
    caller.say("आपका समय क्या है")
    caller.say("कल")
    assert not caller.escalated
    assert WEEKDAYS_HI[_day(1).weekday()] in caller.reply and "बंद" in caller.reply


def test_yes_after_the_booking_offer_continues_into_booking():
    caller = Convo(make_db(closed_offsets=(1,)))
    caller.say("what are your timings")
    caller.say("tomorrow")
    caller.say("yes")
    assert not caller.escalated
    assert caller.reply == "Sure. Which day and time would you prefer?"
    assert caller.state == "booking_day"


# ---------------------------------------------------------------------------------------
# booking: closed day, corrected day, spoken times, bare "9:30" + "confirm"
# ---------------------------------------------------------------------------------------

def test_closed_day_is_reported_before_asking_for_a_time():
    caller = Convo(make_db(closed_offsets=(1,)))
    caller.say("I want to book an appointment")
    caller.say("tomorrow")
    assert caller.reply.startswith(f"Tomorrow is {WEEKDAYS_EN[_day(1).weekday()]}, and we're closed.")
    assert caller.reply.endswith("Which day would you prefer instead?")
    assert caller.state == "booking_day" and not caller.escalated


def test_correcting_the_day_replaces_the_old_one():
    caller = Convo(make_db(closed_offsets=(1,)))
    caller.say("I want to book an appointment")
    caller.say("tomorrow")
    target = _day(2)
    caller.say(WEEKDAYS_EN[target.weekday()])
    result = caller.say("10 am")
    assert "Shall I confirm" in caller.reply
    assert result["booking"]["date"] == target.isoformat()     # not the closed "tomorrow"


def test_bare_nine_thirty_then_confirm_completes():
    caller = Convo(make_db())
    caller.say("I want to book an appointment")
    caller.say(WEEKDAYS_EN[_day(2).weekday()])
    caller.say("9:30")
    assert "9:30 AM" in caller.reply and "Shall I confirm" in caller.reply
    result = caller.say("yes confirm")
    assert result["booking"]["confirmation_requested"] is True
    assert result["booking"]["time"] == "9:30 AM"               # AM/PM resolved, so the booking code can parse it
    assert result["booking"]["date"] == _day(2).isoformat()
    assert not caller.escalated


@pytest.mark.parametrize("utterance,expected_time", [
    ("{day} 9 30 am please", "9:30 AM"),
    ("can I come on {day} morning at half past nine", "9:30 AM"),
    ("book me for {day} at nine thirty", "9:30 AM"),
    ("I want an appointment {day} ten o'clock", "10 AM"),
])
def test_spoken_times_start_and_complete_a_booking(utterance, expected_time):
    day = WEEKDAYS_EN[_day(2).weekday()]
    caller = Convo(make_db())
    result = caller.say(utterance.format(day=day))
    assert not caller.escalated and "Shall I confirm" in caller.reply
    assert expected_time in caller.reply and result["booking"]["date"] == _day(2).isoformat()


def test_booking_wording_has_no_on_tomorrow():
    caller = Convo(make_db())
    caller.say("I want to book an appointment")
    caller.say("tomorrow")
    assert "on tomorrow" not in caller.reply.lower()
    assert "tomorrow" in caller.reply.lower()


# ---------------------------------------------------------------------------------------
# library precision / recall (no AI): never a confident wrong answer, find word forms and typos
# ---------------------------------------------------------------------------------------

def test_function_words_cannot_create_a_library_match():
    db = make_db()
    assert knowledge_match(db, "t1", "is tomorrow a holiday") is None
    assert knowledge_match(db, "t1", "what is the weather like") is None
    assert knowledge_match(db, "t1", "is there a swimming pool") is None


@pytest.mark.parametrize("question", ["is there parking", "can I park my car", "do you have parkng", "where can visitors park"])
def test_library_finds_word_forms_and_typos(question):
    assert "Free parking" in knowledge_match(make_db(), "t1", question)


def test_library_still_answers_plain_questions():
    assert "Lake View Road" in knowledge_match(make_db(), "t1", "where are you located")


def test_unanswerable_question_still_escalates_honestly():
    caller = Convo(make_db())
    caller.say("do you have a swimming pool")
    assert caller.escalated and caller.last["provider"] == "none"


# ---------------------------------------------------------------------------------------
# the real production call (2026-10-11): "10 10" after "What time would you prefer?" was
# not understood, escalated to the paid specialist, and the call never recovered
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("10 10", "10:10"), ("1010", "10:10"), ("930", "9:30"), ("10 30", "10:30"), ("10.30", "10:30"),
    ("11", "11"), ("ten ten", "10:10"), ("ten thirty", "10:30"), ("eleven", "11"), ("at 3 30 pm", "3:30 PM"),
    ("10 pm", "10 PM"), ("nine forty five", "9:45"), ("10 10 please", "10:10"),
])
def test_bare_answers_to_what_time(text, expected):
    assert bare_time_answer(text) == expected


@pytest.mark.parametrize("text", ["I want 11 tickets", "tomorrow", "yes", "13 40", "2026", "what are your timings", ""])
def test_other_things_are_not_taken_for_a_time(text):
    assert bare_time_answer(text) is None


def test_only_a_what_time_question_makes_a_bare_number_a_time():
    assert asks_for_time("Sure. What time would you prefer tomorrow?")
    assert asks_for_time("Which time works for you?")
    assert not asks_for_time("Sure. Which day and time would you prefer?")   # a bare number could be a date here
    assert not asks_for_time("We're open Monday to Saturday.")
    assert not asks_for_time(None)
    assert brain.extract_booking_entities("10 10")["time"] is None            # on its own it is just two numbers
    assert brain.extract_booking_entities("10 10", expecting_time=True)["time"] == "10:10"


@pytest.mark.parametrize("answer,shown", [
    ("10 10", "10:10 AM"), ("1010", "10:10 AM"), ("ten ten", "10:10 AM"), ("930", "9:30 AM"),
    ("10 30", "10:30 AM"), ("11", "11 AM"),
])
def test_the_real_call_does_not_escalate_on_a_bare_time(answer, shown):
    caller = Convo(make_db())
    caller.say("wanted to know the timings")
    caller.say("appointment for tomorrow")
    assert caller.reply == "Sure. What time would you prefer tomorrow?"
    result = caller.say(answer)
    assert not caller.escalated and caller.last["provider"] == "deterministic"
    assert caller.state == "booking_confirmation"
    assert f"at {shown}" in caller.reply and "Shall I confirm" in caller.reply
    assert result["booking"]["date"] == _day(1).isoformat()


def test_a_time_given_without_a_colon_survives_a_later_day_change():
    caller = Convo(make_db())
    caller.say("appointment for tomorrow")
    caller.say("10 10")
    target = _day(2)
    caller.say(WEEKDAYS_EN[target.weekday()])
    assert "10:10 AM" in caller.reply and not caller.escalated
    assert caller.last["booking"]["date"] == target.isoformat()


def test_confirming_after_a_colonless_time_completes_the_booking():
    caller = Convo(make_db())
    caller.say("appointment for tomorrow")
    caller.say("10 10")
    result = caller.say("yes confirm")
    assert result["booking"]["confirmation_requested"] is True
    assert result["booking"]["time"] == "10:10 AM" and result["booking"]["date"] == _day(1).isoformat()


def test_a_bare_number_is_not_a_time_when_the_assistant_asked_for_the_day_too():
    caller = Convo(make_db())
    caller.say("I want to book an appointment")           # "Which day and time would you prefer?"
    caller.say("11")
    assert "11 AM" not in caller.reply and "11:00" not in caller.reply


# ---------------------------------------------------------------------------------------
# specialist hand-over: no second welcome greeting
# ---------------------------------------------------------------------------------------

def test_specialist_is_told_not_to_greet_again():
    from app.voice_escalate import OPENING_ADDENDUM
    text = OPENING_ADDENDUM.casefold()
    assert "do not give a welcome greeting" in text and "continue it" in text
    assert "taking over" not in text and "greet the customer by name" not in text
