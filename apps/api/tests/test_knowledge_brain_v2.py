from app.knowledge_brain_v2 import classify, extract_entities, industry_intents

def test_v2_booking_and_entities():
    r = classify("I want to book an appointment tomorrow at 10 AM")
    assert r.intent == "BOOK"
    assert r.confidence >= 0.9
    assert r.entities["date"] == "tomorrow"
    assert r.entities["time"] == "10 am"

def test_v2_human_and_voice_feedback():
    assert classify("Can you hear me?").intent == "VOICE_FEEDBACK"
    assert classify("I want to talk to a human").intent == "REQUEST_HUMAN"

def test_v2_unknown_is_safe():
    r = classify("xyz random request")
    assert r.intent == "UNKNOWN"
    assert r.confidence == 0.0

def test_v2_industry_pack_is_additive():
    assert "TABLE_RESERVATION" in industry_intents("restaurant")
    assert "DOCTOR_INFORMATION" in industry_intents("clinic")
    assert "MEMBERSHIP" in industry_intents("gym")

def test_v2_never_invents_missing_entities():
    assert extract_entities("book something sometime") == {}
