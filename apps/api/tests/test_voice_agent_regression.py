"""Deterministic voice-agent regression suite.

This suite intentionally runs before live-provider testing. It validates the
library-first routing and booking entity extraction without consuming AI tokens
or requiring a live Gemini/OpenAI session.

The live browser/realtime suite is a separate layer.
"""

import pytest

from app.brain import local_intent, extract_booking_entities
from app.ai_router import detect_language


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
    ("booking", "appointment please"),\n    ("booking", "Naaku appointment book cheyyali"),\n    ("booking", "Enakku appointment book pannanum"),\n    ("booking", "Nanage appointment book madbeku"),\n    ("booking", "Enikku appointment book cheyyanam"),\n    ("booking", "Mala appointment book karaychi aahe"),\n    ("booking", "Ami appointment book korte chai"),\n    ("booking", "Mare appointment book karvi chhe"),
    ("business_hours", "What are your hours"),
    ("business_hours", "What time do you open"),
    ("business_hours", "What time do you close"),
    ("business_hours", "Are you open today"),
    ("business_hours", "What are your timings"),
    ("business_hours", "may I know the timings"),
    ("business_hours", "han may I know the timings"),
    ("business_hours", "Man of the timings"),
    ("business_hours", "Manoj timings"),
    ("business_hours", "may know the timings"),\n    ("business_hours", "Mee timings enti"),\n    ("business_hours", "Unga timings enna"),\n    ("business_hours", "Nimma timings enu"),\n    ("business_hours", "Ningalude timings entha"),\n    ("business_hours", "Tumche timings kay aahet"),\n    ("business_hours", "Apnader timings ki"),\n    ("business_hours", "Tamara timings shu chhe"),\n    ("business_hours", "Tuhade timings ki ne"),
    ("business_hours", "Tell me your timing"),
    ("business_hours", "When are you open"),
    ("business_hours", "When do you finish for the day"),
    ("business_hours", "Do you open in the morning"),
    ("business_hours", "What time do you start"),
    ("doctor_information", "may i know the doctor name"),\n    ("availability", "Is there a slot available"),
    ("availability", "Are you available tomorrow"),
    ("availability", "Can I get a slot"),
    ("availability", "Check availability"),
    ("availability", "Do you have any availability"),
    ("booking", "Is there any appointment available"),
    ("booking", "Can I get an appointment slot"),
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
    ("closing", "please confirm"),
    ("closing", "please confirm the appointment"),
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
    ("tomorrow at 5:30 p.m.", "tomorrow", "5:30 PM"),\n    ("kal 4 baje", None, "4 PM"),\n    ("cal 4 baje", None, "4 PM"),\n    ("repu 4 gantlaki", None, "4 PM"),\n    ("naalai 4 manikku", None, "4 PM"),\n    ("naale 4 gantige", None, "4 PM"),\n    ("udya 4 vajta", None, "4 PM"),\n    ("kaale 4 vagye", None, "4 PM"),
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
    ("8:00 pm", None, "8:00 PM"),
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


@pytest.mark.parametrize("message,expected", [
    ("Can you speak Hindi", "hi"),
    ("Telugulo matladagalara", "te"),
    ("Enakku information venum", "ta"),
    ("Nanage swalpa information beku", "kn"),
    ("Enikku kurachu information venam", "ml"),
    ("Mala thodi mahiti havi aahe", "mr"),
    ("Amar ektu information dorkar", "bn"),
    ("Mane thodi mahiti joiye", "gu"),
    ("Mainu thodi information chahidi hai", "pa"),
])
def test_romanized_language_detection(message, expected):
    assert detect_language(message) == expected


def test_reception_routing_rule_selects_configured_department_and_priority():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import Tenant
    from app.models_ai import Department, StaffMember, RoutingRule
    from app.models_growth import CallRecord
    from app.routing import route_call

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    tenant = Tenant(id="t1", name="Demo", slug="demo", industry="wellness")
    db.add(tenant)
    dept = Department(id="d1", tenant_id="t1", name="Billing", skills="payment,refund")
    staff = StaffMember(id="s1", tenant_id="t1", name="Billing Agent", department_id="d1", skills="refund", is_available=True)
    rule = RoutingRule(id="r1", tenant_id="t1", name="Payment escalation", intent="payment", department_id="d1", staff_id="s1", priority=1, urgency="high", action="route_and_alert")
    call = CallRecord(id="c1", tenant_id="t1", source="webrtc", status="connected", intent="payment", summary="Customer reports a payment issue")
    db.add_all([dept, staff, rule, call])
    db.commit()
    result = route_call(db, "t1", call, "payment")
    assert result["department"] == "Billing"
    assert result["staff"]["id"] == "s1"
    assert result["urgency"] == "high"
    assert result["rule_id"] == "r1"
    db.close()
