from datetime import date, datetime
from types import SimpleNamespace

import app.voice_booking_actions as actions
from app.voice_booking_actions import _action_intent, _affirmative, _negative, _parse_new_start


def test_detects_cancellation_request():
    assert _action_intent("Please cancel my appointment") == "cancel"


def test_detects_rescheduling_request():
    assert _action_intent("Can you reschedule my appointment to Monday?") == "reschedule"
    assert _action_intent("Change my appointment time") == "reschedule"


def test_does_not_treat_unrelated_message_as_appointment_action():
    assert _action_intent("What are your opening hours?") is None


def test_explicit_confirmation_is_narrow():
    assert _affirmative("Yes, please")
    assert _affirmative("हाँ")
    assert not _affirmative("yes, but maybe later")
    assert _negative("No thanks")
    assert not _negative("No, actually yes")

def test_recognizes_natural_reschedule_phrasing():
    assert _action_intent("Can I change the timing of my appointment?") == "reschedule"
    assert _action_intent("Move it to Monday at 11 AM") == "reschedule"

def test_reschedule_parser_requires_explicit_am_pm(monkeypatch):
    monkeypatch.setattr(actions, "extract_booking_entities", lambda text: {
        "day": "Monday", "relative_day": None, "date_hint": None, "time": "11:00"
    })
    monkeypatch.setattr(actions, "resolve_booking_date", lambda tenant, day, relative, hint: date(2026, 10, 12))
    tenant = SimpleNamespace(timezone="Asia/Kolkata")
    assert _parse_new_start(tenant, "Monday at 11") is None


def test_reschedule_parser_converts_explicit_time(monkeypatch):
    monkeypatch.setattr(actions, "extract_booking_entities", lambda text: {
        "day": "Monday", "relative_day": None, "date_hint": None, "time": "11:00 AM"
    })
    monkeypatch.setattr(actions, "resolve_booking_date", lambda tenant, day, relative, hint: date(2026, 10, 12))
    tenant = SimpleNamespace(timezone="Asia/Kolkata")
    assert _parse_new_start(tenant, "Monday at 11 AM") == datetime(2026, 10, 12, 11, 0)
