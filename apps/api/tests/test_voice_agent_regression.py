"""Deterministic voice-agent regression suite.

This suite intentionally runs before live-provider testing. It validates the
library-first routing and booking entity extraction without consuming AI tokens
or requiring a live Gemini/OpenAI session.

The live browser/realtime suite is a separate layer.
"""

import pytest

from app.brain import local_intent, extract_booking_entities


INTENT_CASES = [
    ("booking", "I want to book an appointment"),
    ("booking", "Can I schedule a visit"),
    ("booking", "I need an appointment"),
    ("booking", "Can I reserve a slot"),
    ("booking", "I'd like to make a booking"),
    ("booking", "Book me for tomorrow"),
    ("booking", "I want to schedule today"),
    ("booking", "Can I book Thursday"),
    ("booking", "I need to reserve a time"),
    ("booking", "appointment please"),
    ("business_hours", "What are your hours"),
    ("business_hours", "What time do you open"),
    ("business_hours", "What time do you close"),
    ("business_hours", "Are you open today"),
    ("business_hours", "What are your timings"),
    ("business_hours", "Tell me your timing"),
    ("business_hours", "When are you open"),
    ("business_hours", "When do you finish for the day"),
    ("business_hours", "Do you open in the morning"),
    ("business_hours", "What time do you start"),
    ("availability", "Is there a slot available"),
    ("availability", "Are you available tomorrow"),
    ("availability", "Can I get a slot"),
    ("availability", "Check availability"),
    ("availability", "Do you have any availability"),
    ("availability", "Is there any appointment available"),
    ("availability", "Can I get an appointment slot"),
    ("availability", "Any slot available today"),
    ("availability", "Are there slots tomorrow"),
    ("availability", "Is there a free time"),
    ("pricing", "How much does it cost"),
    ("pricing", "What is the price"),
    ("pricing", "What is the fee"),
    ("pricing", "Tell me the rate"),
    ("pricing", "How much is it"),
    ("pricing", "What do you charge"),
    ("pricing", "What is the cost"),
    ("pricing", "How much will I pay"),
    ("pricing", "Price please"),
    ("pricing", "What are your fees"),
    ("product", "Can I buy this product"),
    ("product", "I want to order a product"),
    ("product", "Do you have this product"),
    ("product", "Is this product in stock"),
    ("product", "I want to buy something"),
    ("product", "Can I order this"),
    ("product", "What products do you have"),
    ("product", "Do you have stock"),
    ("product", "I want to purchase this"),
    ("product", "Can I order a product"),
    ("human_handoff", "Can I speak to a person"),
    ("human_handoff", "I want to talk to a human"),
    ("human_handoff", "Please connect me to staff"),
    ("human_handoff", "I need an agent"),
    ("human_handoff", "Can someone call me"),
    ("human_handoff", "Let me speak to someone"),
    ("human_handoff", "I need a staff member"),
    ("human_handoff", "Connect me to a person"),
    ("human_handoff", "I want a human"),
    ("human_handoff", "Please have someone call me"),
    ("closing", "Thank you"),
    ("closing", "Thanks"),
    ("closing", "Goodbye"),
    ("closing", "Bye"),
    ("closing", "That's all"),
    ("closing", "Thats all thank you"),
    ("closing", "Good bye"),
    ("closing", "Thank you very much"),
    ("closing", "Okay bye"),
    ("closing", "Thanks bye"),
    ("language_request", "Can you speak Hindi"),
    ("language_request", "Speak in Hindi"),
    ("language_request", "I want Hindi"),
    ("language_request", "Can we talk in Hindi"),
    ("language_request", "Please speak Hindi"),
    ("language_request", "हिंदी में बात करें"),
    ("language_request", "क्या आप हिंदी बोल सकते हैं"),
    ("language_request", "Hindi please"),
    ("language_request", "Can you reply in Hindi"),
    ("language_request", "Talk to me in Hindi"),
    ("information", "What services do you provide"),
    ("information", "Tell me about the business"),
    ("information", "Where are you located"),
    ("information", "What do you offer"),
    ("information", "Tell me more"),
    ("information", "Can you help me"),
    ("information", "I have a question"),
    ("information", "May I know more details"),
    ("information", "What do you do"),
    ("information", "Tell me about your services"),
]


@pytest.mark.parametrize("expected,message", INTENT_CASES)
def test_voice_intent_matrix(expected, message):
    assert local_intent(message) == expected


BOOKING_EXTRACTION_CASES = [
    ("tomorrow at 5:30 p.m.", "tomorrow", "5:30 PM"),
    ("today at 3 PM", "today", "3 PM"),
    ("Thursday at 4:15 PM", "thursday", "4:15 PM"),
    ("Friday 10 AM", "friday", "10 AM"),
    ("Saturday evening", "saturday", None),
    ("Sunday morning", "sunday", None),
    ("day after tomorrow at 6 PM", "day_after_tomorrow", "6 PM"),
    ("tomorrow at noon", "tomorrow", "12 PM"),
    ("17:30", None, "5:30 PM"),
    ("9:45 AM", None, "9:45 AM"),
    ("12 PM", None, "12 PM"),
    ("8:00 pm", None, "8 PM"),
    ("Wednesday", "wednesday", None),
    ("next Tuesday", "tuesday", None),
    ("Friday night", "friday", None),
    ("today around five", "today", None),
    ("tomorrow at five in the evening", "tomorrow", "5 PM"),
    ("Saturday at 11", "saturday", None),
    ("the 29th", None, None),
    ("30th", None, None),
]


@pytest.mark.parametrize("message,expected_day,expected_time", BOOKING_EXTRACTION_CASES)
def test_booking_entity_extraction(message, expected_day, expected_time):
    result = extract_booking_entities(message)
    expected_relative = expected_day if expected_day in {"today","tomorrow","day_after_tomorrow"} else None
    expected_weekday = None if expected_relative else (None if expected_day == "null" else expected_day)
    assert result["day"] == expected_weekday
    assert result["relative_day"] == expected_relative
    assert result["time"] == expected_time


def test_regression_suite_has_more_than_100_scenarios():
    assert len(INTENT_CASES) + len(BOOKING_EXTRACTION_CASES) >= 100
