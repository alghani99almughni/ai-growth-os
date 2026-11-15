from datetime import date, datetime, time
from types import SimpleNamespace

from app.voice_booking_time import call_local_datetime, resolve_voice_time


def hours(opening, closing, closed=False):
    return SimpleNamespace(open_time=time.fromisoformat(opening),
                           close_time=time.fromisoformat(closing),
                           is_closed=closed)


CALL = datetime(2026, 11, 15, 10, 0)  # 15:30 in Asia/Kolkata


def test_call_timestamp_is_converted_from_utc_to_tenant_timezone():
    assert call_local_datetime(CALL, "Asia/Kolkata") == datetime(2026, 11, 15, 15, 30)


def test_business_hours_resolve_only_valid_pm_interpretation():
    result = resolve_voice_time("5:30 PM", "CUSTOMER: book tomorrow at 5:30",
                                hours("09:00", "18:00"), date(2026, 11, 16), CALL)
    assert result["status"] == "resolved"
    assert result["time"] == time(17, 30)
    assert result["explicit"] is False


def test_explicit_customer_am_is_never_rewritten():
    result = resolve_voice_time("5:30 PM", "CUSTOMER: 5:30 AM please",
                                hours("09:00", "18:00"), date(2026, 11, 16), CALL)
    assert result["status"] == "resolved"
    assert result["time"] == time(5, 30)
    assert result["explicit"] is True


def test_latest_explicit_customer_correction_wins():
    transcript = "CUSTOMER: book for 9 AM\nCUSTOMER: sorry, make that 9 PM"
    result = resolve_voice_time("9 AM", transcript, hours("00:00", "23:59"),
                                date(2026, 11, 16), CALL)
    assert result["status"] == "resolved"
    assert result["time"] == time(21, 0)


def test_spoken_local_language_time_marker_is_preserved():
    result = resolve_voice_time("5:30 PM", "CUSTOMER: 5:30 ఉదయం",
                                hours("09:00", "18:00"), date(2026, 11, 16), CALL)
    assert result["status"] == "resolved"
    assert result["time"] == time(5, 30)


def test_assistant_meridian_does_not_override_bare_customer_time():
    transcript = "CUSTOMER: 5:30 please\nAI: Did you mean 5:30 PM?"
    result = resolve_voice_time("5:30 PM", transcript, hours("09:00", "18:00"),
                                date(2026, 11, 16), CALL)
    assert result["status"] == "resolved"
    assert result["time"] == time(17, 30)
    assert result["explicit"] is False


def test_247_business_requires_am_pm_clarification():
    result = resolve_voice_time("5:30", "CUSTOMER: 5:30",
                                hours("00:00", "23:59"), date(2026, 11, 16), CALL)
    assert result["status"] == "clarification_required"
    assert result["valid_candidates"] == ["05:30", "17:30"]


def test_neither_interpretation_in_hours_requires_clarification():
    result = resolve_voice_time("5:30", "CUSTOMER: 5:30",
                                hours("09:00", "12:00"), date(2026, 11, 16), CALL)
    assert result["status"] == "clarification_required"
    assert result["valid_candidates"] == []


def test_call_time_excludes_past_am_candidate_for_same_day():
    local_call = datetime(2026, 11, 15, 16, 45)
    result = resolve_voice_time("5:30", "CUSTOMER: today at 5:30",
                                hours("09:00", "18:00"), date(2026, 11, 15), local_call)
    assert result["status"] == "resolved"
    assert result["time"] == time(17, 30)


def test_explicit_24_hour_time_is_unambiguous():
    result = resolve_voice_time("17:30", "CUSTOMER: 17:30",
                                hours("00:00", "23:59"), date(2026, 11, 16), CALL)
    assert result["status"] == "resolved"
    assert result["time"] == time(17, 30)
