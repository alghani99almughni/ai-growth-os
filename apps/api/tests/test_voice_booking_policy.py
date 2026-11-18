from datetime import date, datetime, time
from types import SimpleNamespace

from app.voice_booking_policy import evaluate_last_minute


class _PolicyDb:
    def __init__(self, window_minutes, close_time=time(23, 0), is_closed=False):
        self.rows = [
            SimpleNamespace(value_json='{"last_minute_window_minutes": %d, "handoff_enabled": true}' % window_minutes),
            SimpleNamespace(close_time=close_time, is_closed=is_closed),
        ]

    def scalar(self, _query):
        return self.rows.pop(0)


def test_last_minute_window_uses_tenant_configured_30_minutes_and_call_start():
    tenant = SimpleNamespace(id="tenant-a", timezone="Asia/Kolkata")
    # 22:35 IST; closing is 23:00, so the 30-minute rule applies.
    decision = evaluate_last_minute(
        _PolicyDb(30), tenant, datetime(2026, 11, 19, 17, 5),
        date(2026, 11, 19), time(22, 45),
    )
    assert decision.is_last_minute is True
    assert decision.window_minutes == 30
    assert decision.minutes_until_close == 25


def test_last_minute_window_uses_tenant_configured_15_minutes():
    tenant = SimpleNamespace(id="tenant-a", timezone="Asia/Kolkata")
    decision = evaluate_last_minute(
        _PolicyDb(15), tenant, datetime(2026, 11, 19, 17, 40),
        date(2026, 11, 19), time(22, 50),
    )
    assert decision.is_last_minute is True
    assert decision.window_minutes == 15
    assert decision.minutes_until_close == 10


def test_call_started_outside_same_local_day_is_not_last_minute():
    tenant = SimpleNamespace(id="tenant-a", timezone="Asia/Kolkata")
    decision = evaluate_last_minute(
        _PolicyDb(30), tenant, datetime(2026, 11, 18, 17, 5),
        date(2026, 11, 19), time(22, 45),
    )
    assert decision.is_last_minute is False
    assert decision.reason == "not_same_day"


def test_closed_day_does_not_trigger_closing_buffer():
    tenant = SimpleNamespace(id="tenant-a", timezone="Asia/Kolkata")
    decision = evaluate_last_minute(
        _PolicyDb(30, is_closed=True), tenant, datetime(2026, 11, 19, 17, 5),
        date(2026, 11, 19), time(22, 45),
    )
    assert decision.is_last_minute is False
    assert decision.reason == "closed_or_unconfigured"
