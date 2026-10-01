from app.agent_scenarios import (
    INTENTS,
    INDUSTRY_TEMPLATES,
    QUESTION_LIBRARY,
    UNIVERSAL_SCENARIOS,
    build_training_matrix,
    TIME_SCENARIOS,
)


def test_all_required_intents_are_present():
    assert INTENTS == ("WHAT", "IF", "NOW", "WHEN", "WHERE", "WHY", "HOW", "WHOM", "WHO")
    assert all(QUESTION_LIBRARY[intent] for intent in INTENTS)


def test_required_question_families_are_represented():
    required = {
        "What services do you provide?",
        "What time are you open?",
        "What are the charges?",
        "If the time slot is not available today, what can I do?",
        "If I am late, will my appointment still be considered?",
        "Now can I book the appointment?",
        "Now can you cancel the booking?",
        "It is outside office hours. Can I get an emergency appointment?",
        "When can I see the doctor?",
        "When can I get my order?",
        "When will someone call me back?",
        "Where are you located?",
        "Why is the doctor not available?",
        "Why is your service delayed?",
        "Why can't you take bookings?",
        "How will I get support?",
        "How will I get my bill?",
        "How will I get a refund?",
        "How can I make the payment?",
        "How do I reach you?",
        "Whom should I contact?",
        "Who will handle my enquiry?",
        "Who will call me back?",
        "Who will change my appointment?",
    }
    actual = {q for questions in QUESTION_LIBRARY.values() for q in questions}
    assert required <= actual


def test_universal_safety_scenarios_cover_core_risks():
    ids = {scenario.id for scenario in UNIVERSAL_SCENARIOS}
    assert {
        "availability_alternative",
        "staff_unavailable",
        "late_arrival",
        "outside_hours_emergency",
        "callback",
        "cancel",
        "delay_reason",
        "high_charge",
        "cannot_book",
        "refund",
        "responsibility",
        "human_contact",
        "ambiguous_time",
        "explicit_time_am",
        "explicit_time_pm",
        "time_boundary",
        "unknown_reason",
        "cross_tenant",
    } <= ids


def test_fifteen_industry_templates_exist():
    assert len(INDUSTRY_TEMPLATES) == 15
    assert len(set(INDUSTRY_TEMPLATES)) == 15


def test_training_matrix_is_non_empty_and_industry_aware():
    matrix = build_training_matrix()
    assert len(matrix) >= 150
    industries = {row["industry"] for row in matrix if row["type"] == "industry"}
    assert industries == set(INDUSTRY_TEMPLATES)


def test_scenarios_never_instruct_the_agent_to_invent_facts():
    for scenario in UNIVERSAL_SCENARIOS:
        joined = " ".join(scenario.expected).lower()
        assert "never_invent" in joined or "do_not" in joined or "unknown" in joined or "only" in joined



def test_full_24_hour_time_matrix():
    assert len(TIME_SCENARIOS) == 24
    prompts = {s.prompt for s in TIME_SCENARIOS}
    assert "Book me for 1 AM." in prompts
    assert "Book me for 12 AM." in prompts
    assert "Book me for 1 PM." in prompts
    assert "Book me for 12 PM." in prompts
    for scenario in TIME_SCENARIOS:
        assert "check_business_hours" in scenario.expected
        assert "check_live_availability" in scenario.expected
        assert "confirm_before_booking" in scenario.expected
        assert "do_not_book_if_outside_business_hours" in scenario.expected
