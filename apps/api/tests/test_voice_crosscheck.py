from app.voice_crosscheck import LIVE_DATA_INTENTS, crosscheck_turn


def test_voice_crosscheck_is_fast_and_classifies():
    r = crosscheck_turn("Can you check a slot tomorrow at 4 PM?", "clinic")
    assert r.intent in {"CHECK_AVAILABILITY", "BOOK"}
    assert r.confidence >= 0.9
    assert r.live_data_required is True
    assert r.latency_ms < 100


def test_voice_crosscheck_unknown_is_safe():
    r = crosscheck_turn("xyz random request")
    assert r.intent == "UNKNOWN"
    assert r.live_data_required is False
    assert r.entities == {}


def test_live_data_intents_are_explicit():
    assert "CHECK_AVAILABILITY" in LIVE_DATA_INTENTS
    assert "CONFIRM_BOOKING" in LIVE_DATA_INTENTS
