from app.global_knowledge import CORE_INTENTS, INDUSTRY_INTENTS, canonical_intent


def test_legacy_knowledge_intents_map_to_canonical_without_changing_names():
    assert canonical_intent("What time do you open?", "business_hours") == "GET_HOURS"
    assert canonical_intent("How much is the consultation?", "pricing") == "GET_PRICE"
    assert canonical_intent("Can I speak to a person?", "human_handoff") == "REQUEST_HUMAN"


def test_global_intent_taxonomy_covers_common_customer_goals():
    assert {"BOOK", "CHECK_AVAILABILITY", "PAYMENT_STATUS", "CURRENT_OFFERS",
            "REQUEST_HUMAN", "VOICE_FEEDBACK", "UNKNOWN"} <= CORE_INTENTS


def test_global_classifier_handles_new_topics():
    assert canonical_intent("Where is my order?") == "ORDER_TRACKING"
    assert canonical_intent("Do you have any discount today?") == "CURRENT_OFFERS"
    assert canonical_intent("Can you repeat that?") == "REPEAT_REQUEST"


def test_industry_pack_is_optional_and_does_not_change_unknown_fallback():
    assert canonical_intent("I need information", industry="clinic") == "UNKNOWN"
    assert "DOCTOR_INFORMATION" in INDUSTRY_INTENTS["clinic"]
