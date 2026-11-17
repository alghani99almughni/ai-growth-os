from datetime import date, datetime, time
from types import SimpleNamespace

import app.voice_booking_actions as actions
from app.voice_booking_actions import _action_intent, _affirmative, _negative, _parse_new_start


def _parser_context(opening="09:00", closing="18:00"):
    tenant = SimpleNamespace(id="tenant-1", timezone="Asia/Kolkata")
    call = SimpleNamespace(
        started_at=datetime(2026, 10, 11, 10, 0),  # 15:30 in Asia/Kolkata
        transcript="",
    )
    business_hours = SimpleNamespace(
        open_time=time.fromisoformat(opening),
        close_time=time.fromisoformat(closing),
        is_closed=False,
    )
    db = SimpleNamespace(scalar=lambda _query: business_hours)
    return db, tenant, call


def _mock_entities(monkeypatch, spoken_time):
    monkeypatch.setattr(actions, "extract_booking_entities", lambda _text: {
        "day": "Monday", "relative_day": None, "date_hint": None, "time": spoken_time
    })
    monkeypatch.setattr(
        actions, "resolve_booking_date",
        lambda tenant, day, relative, hint, reference_datetime=None: date(2026, 10, 12),
    )


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


def test_reschedule_parser_requires_am_pm_for_247_business(monkeypatch):
    _mock_entities(monkeypatch, "11:00")
    db, tenant, call = _parser_context("00:00", "23:59")

    parsed = _parse_new_start(db, tenant, call, "Monday at 11")

    assert parsed["status"] == "clarification_required"
    assert parsed["date"] == date(2026, 10, 12)
    assert parsed["time"] == "11:00"


def test_reschedule_parser_converts_explicit_time(monkeypatch):
    _mock_entities(monkeypatch, "11:00 AM")
    db, tenant, call = _parser_context()

    parsed = _parse_new_start(db, tenant, call, "Monday at 11 AM")

    assert parsed["status"] == "resolved"
    assert parsed["starts_at"] == datetime(2026, 10, 12, 11, 0)


def test_reschedule_parser_uses_business_hours_to_resolve_unique_meridian(monkeypatch):
    _mock_entities(monkeypatch, "5:30")
    db, tenant, call = _parser_context("09:00", "18:00")

    parsed = _parse_new_start(db, tenant, call, "Monday at 5:30")

    assert parsed["status"] == "resolved"
    assert parsed["starts_at"] == datetime(2026, 10, 12, 17, 30)



def test_reschedule_parser_uses_customer_call_time_for_same_day_meridian(monkeypatch):
    captured = {}
    monkeypatch.setattr(actions, "extract_booking_entities", lambda _text: {
        "day": "today", "relative_day": "today", "date_hint": None, "time": "5:30"
    })

    def resolve_date(_tenant, _day, _relative, _hint, reference_datetime=None):
        captured["reference_datetime"] = reference_datetime
        return date(2026, 10, 11)

    monkeypatch.setattr(actions, "resolve_booking_date", resolve_date)
    db, tenant, call = _parser_context("00:00", "23:59")

    parsed = _parse_new_start(db, tenant, call, "Today at 5:30")

    # Persisted call time is 10:00 UTC = 15:30 in the tenant's timezone.
    assert captured["reference_datetime"] == datetime(2026, 10, 11, 15, 30)
    # The call timestamp is passed into date resolution, but a 24/7 tenant
    # must still ask the caller to choose AM or PM rather than guessing.
    assert parsed["status"] == "clarification_required"
    assert parsed["date"] == date(2026, 10, 11)
    assert parsed["time"] == "5:30"
    assert parsed["candidates"] == ["05:30", "17:30"]
