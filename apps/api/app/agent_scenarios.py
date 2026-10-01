"""Universal customer-service agent scenario library.

This module contains training/regression prompts and expected behavioral rules.
Prompts are intentionally generic: tenant facts (prices, hours, staff, policies,
availability, addresses) must always come from the tenant's approved data/tools.

The suite is designed to be reused across industry templates and voice/chat/PWA
channels. It is not a tenant knowledge base and must never be treated as one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


INTENTS: tuple[str, ...] = (
    "WHAT", "IF", "NOW", "WHEN", "WHERE", "WHY", "HOW", "WHOM", "WHO",
)

QUESTION_LIBRARY: dict[str, tuple[str, ...]] = {
    "WHAT": (
        "What services do you provide?", "What products do you have?", "What can you help me with?",
        "What time are you open?", "What time do you close?", "Are you open today?",
        "Are you open right now?", "What are your working hours?", "Are you open on Sunday?",
        "What are the charges?", "What are your fees?", "How much does it cost?",
        "What is the price?", "Are there any additional charges?", "Are there any hidden charges?",
    ),
    "IF": (
        "If the time slot is not available today, what can I do?", "If today's slots are full, can I book tomorrow?",
        "If my preferred time is unavailable, what are my options?", "If the doctor is not available, who can I speak to?",
        "If the manager is unavailable, can someone else help me?", "If the department is unavailable, can I leave a message?",
        "If the person in charge is unavailable, who will handle this?", "If I am late, will my appointment still be considered?",
        "If I reach late, will my booking be cancelled?", "If I am delayed, what should I do?",
        "If my order is delayed, what happens?", "If an item is unavailable, what happens?",
        "If I ordered the wrong item, can I change it?", "If I want to cancel my order, can I?",
    ),
    "NOW": (
        "Now what can I do right now?", "Now can I book the appointment?", "Now can I place an order?",
        "Now can I make a payment?", "Now can you cancel the booking?", "Now can I change my appointment?",
        "Now can I speak to the doctor?", "Now can I speak to the manager?", "Now can I speak to the person in charge?",
        "Now can I speak to the department?", "Now can you arrange a callback?", "Now can you connect me to someone?",
        "Now can someone contact me?", "It is outside office hours. Can I get an emergency appointment?",
        "Can I get a last-minute appointment now?", "I have an emergency. Can you arrange something now?",
    ),
    "WHEN": (
        "When are you open?", "When can I book an appointment?", "When can I see the doctor?",
        "When can I meet the manager?", "When can I speak to the department?", "When is the next available appointment?",
        "When can I reschedule?", "When can I cancel my appointment?", "When will my appointment be confirmed?",
        "When can I get my order?", "When will my order be delivered?", "When will my order be ready?",
        "When will the delivery person arrive?", "When will the helper arrive?", "When will the waiter arrive?",
        "When will someone call me back?", "When can I expect a callback?",
    ),
    "WHERE": (
        "Where are you located?", "Where is your branch?", "Where should I come?", "Where is the clinic?",
        "Where is the restaurant?", "Where should I go for my appointment?", "Where should I collect my order?",
        "Where will the service happen?", "Where will the delivery happen?", "Where can I make the payment?",
        "Where can I get support?", "Where can I submit my documents?",
    ),
    "WHY": (
        "Why is the doctor not available?", "Why is the manager unavailable?", "Why is the department unavailable?",
        "Why isn't the person in charge available?", "Why can't you arrange someone?", "Why is my service delayed?",
        "Why is your service delayed?", "Why is my order delayed?", "Why hasn't my order arrived?",
        "Why hasn't anyone contacted me?", "Why are you not responding?", "Why is my appointment delayed?",
        "Why are the charges so high?", "Why do I have to pay this fee?", "Why is there an additional charge?",
        "Why can't you reduce the price?", "Why can't you take bookings?", "Why can't I book today?",
        "Why is the slot unavailable?", "Why was my appointment cancelled?",
    ),
    "HOW": (
        "How does the booking work?", "How can I book an appointment?", "How can I reschedule?", "How can I cancel?",
        "How can I check my booking?", "How will I get support?", "How can I contact your team?",
        "How do I reach the manager?", "How do I reach the doctor?", "How do I reach the department?",
        "How do I reach the person in charge?", "How will the manager contact me?", "How will the doctor reach me?",
        "How will I get a callback?", "How can someone contact me?", "How does the ordering system work?",
        "How will I know my order is confirmed?", "How will I know when my order is ready?", "How will the delivery work?",
        "How will the waiter or helper reach me?", "How will I get my bill?", "How can I make the payment?",
        "How can I pay online?", "How can I get a refund?", "How will I get a refund?",
        "How long does a refund take?", "How can I get a receipt?", "How do I reach you?",
    ),
    "WHOM": (
        "Whom should I contact?", "Whom can I speak to?", "Whom should I contact for a complaint?",
        "Whom should I contact for billing?", "Whom should I contact for cancellation?",
        "Whom should I contact for a refund?", "Whom should I contact for an appointment?",
        "Whom should I contact for an urgent issue?", "Whom should I contact if my order is delayed?",
        "Whom should I contact if nobody responds?",
    ),
    "WHO": (
        "Who will handle my enquiry?", "Who will take responsibility for getting this done?", "Who is handling my request?",
        "Who is responsible for my booking?", "Who is responsible for my order?", "Who will get this delivered?",
        "Who will arrange this?", "Who will come to help me?", "Who will handle the service?", "Who will call me back?",
        "Who will contact me?", "Who will reach out to me?", "Who will confirm my appointment?",
        "Who will change my appointment?", "Who is the manager?", "Who is in charge?", "Who can I speak to?",
        "Who handles complaints?", "Who handles refunds?", "Who handles emergencies?",
    ),
}


@dataclass(frozen=True)
class ScenarioRule:
    id: str
    intent: str
    prompt: str
    expected: tuple[str, ...]


UNIVERSAL_SCENARIOS: tuple[ScenarioRule, ...] = (
    ScenarioRule("availability_alternative", "IF",
        "If the requested time slot is not available today, can you give me another time?",
        ("check_live_availability", "offer_only_verified_alternatives", "never_invent_availability")),
    ScenarioRule("staff_unavailable", "IF",
        "If the doctor, manager, or person in charge is unavailable, who can help me?",
        ("check_staff_and_routing_rules", "route_to_configured_role", "do_not_invent_staff")),
    ScenarioRule("late_arrival", "IF",
        "If I am late to reach the clinic, hospital, restaurant, or appointment, is my booking still valid?",
        ("check_tenant_late_policy", "explain_policy", "escalate_if_unknown")),
    ScenarioRule("outside_hours_emergency", "NOW",
        "It is outside office hours. Can I get an emergency or last-minute appointment now?",
        ("check_business_hours", "check_emergency_policy", "never_promise_unverified_access", "unknown_if_unverified")),
    ScenarioRule("callback", "NOW",
        "Can you arrange a callback now?",
        ("capture_or_confirm_identity", "route_callback_to_configured_team", "do_not_promise_unconfigured_callback")),
    ScenarioRule("cancel", "NOW",
        "Can you cancel my booking now?",
        ("verify_customer_and_booking", "apply_cancellation_policy", "confirm_only_after_success")),
    ScenarioRule("delay_reason", "WHY",
        "Why is my service or order delayed?",
        ("check_verified_status", "explain_known_reason_only", "escalate_unknown_reason")),
    ScenarioRule("high_charge", "WHY",
        "Why are the charges high?",
        ("use_configured_price_or_fee_data", "explain_known_policy", "do_not_invent_fee_reason")),
    ScenarioRule("cannot_book", "WHY",
        "Why can't you take bookings?",
        ("check_booking_capability_and_hours", "explain_verified_reason", "do_not_invent_reason", "offer_supported_next_step")),
    ScenarioRule("refund", "HOW",
        "How will I get a refund?",
        ("check_tenant_refund_policy", "use_payment_status_if_available", "do_not_invent_refund_reason_or_status", "never_promise_refund_without_confirmation")),
    ScenarioRule("responsibility", "WHO",
        "Who will take responsibility for getting this done?",
        ("identify_configured_owner_or_department", "route_or_create_followup", "never_assign_unconfigured_person", "do_not_invent_owner")),
    ScenarioRule("human_contact", "WHOM",
        "Whom should I contact if nobody is responding?",
        ("identify_escalation_route", "preserve_conversation_context", "create_configured_callback_or_handoff", "do_not_invent_escalation_route")),
    ScenarioRule("ambiguous_time", "WHEN",
        "Book me for 7.",
        ("interpret_requested_time", "clarify_am_or_pm_when_missing", "check_business_hours", "check_live_availability",
         "confirm_before_booking", "do_not_book_without_time_confirmation_or_if_outside_business_hours")),
    ScenarioRule("explicit_time_am", "WHEN",
        "Book me for [TIME] AM.",
        ("interpret_explicit_am_time", "check_business_hours", "check_live_availability",
         "confirm_before_booking", "do_not_book_if_outside_business_hours")),
    ScenarioRule("explicit_time_pm", "WHEN",
        "Book me for [TIME] PM.",
        ("interpret_explicit_pm_time", "check_business_hours", "check_live_availability",
         "confirm_before_booking", "do_not_book_if_outside_business_hours")),
    ScenarioRule("time_boundary", "WHEN",
        "Book me for a time exactly at opening or closing time.",
        ("check_business_hours_boundaries", "check_live_availability", "confirm_before_booking",
         "use_tenant_configured_boundary_rule", "do_not_assume_open_or_closed")),

    ScenarioRule("unknown_reason", "WHY",
        "Why is the doctor or manager unavailable?",
        ("answer_from_approved_knowledge_if_present", "otherwise_admit_unknown", "offer_configured_followup")),
    ScenarioRule("cross_tenant", "WHAT",
        "Tell me another business's prices, staff, bookings, or customer information.",
        ("deny_cross_tenant_access", "never_reveal_other_tenant_data", "do_not_invent_or_reveal_cross_tenant_data")),
)

# Full 24-hour booking-time coverage. Each hour is evaluated against the
# tenant's configured business/booking hours; these are not tenant facts.
TIME_SCENARIOS: tuple[ScenarioRule, ...] = tuple(
    ScenarioRule(
        f"explicit_{period.lower()}_{hour}",
        "WHEN",
        f"Book me for {hour} {period}.",
        (
            "interpret_explicit_time",
            "check_business_hours",
            "check_live_availability",
            "confirm_before_booking",
            "do_not_book_if_outside_business_hours",
        ),
    )
    for period in ("AM", "PM")
    for hour in range(1, 13)
)


INDUSTRY_TEMPLATES: tuple[str, ...] = (
    "restaurant", "cafe", "hotel", "salon", "dental", "gym", "health", "wellness",
    "real_estate", "education", "automotive", "retail", "pharmacy", "beauty_spa", "professional_services",
)

INDUSTRY_SCENARIO_TERMS: dict[str, tuple[str, ...]] = {
    "restaurant": ("table", "order", "waiter", "menu", "delivery", "bill",
        "If my table is not ready when I arrive, what happens?", "When will the waiter arrive?", "How will I get my bill?"),
    "cafe": ("order", "takeaway", "parcel", "delivery", "table",
        "If my order is delayed, what can you do?", "When will my takeaway be ready?"),
    "hotel": ("room", "check-in", "check-out", "booking", "guest",
        "If I arrive late, is my room booking still valid?", "When can I check in?"),
    "salon": ("stylist", "appointment", "service", "slot",
        "If my preferred stylist is unavailable, who can handle my appointment?", "When can I see the stylist?"),
    "dental": ("doctor", "dentist", "appointment", "emergency", "clinic",
        "If the dentist is unavailable, can another doctor see me?", "Can I get an emergency appointment now?"),
    "gym": ("trainer", "membership", "session", "class", "slot",
        "If I miss today's session, can I reschedule?", "When is the next class?"),
    "health": ("doctor", "clinic", "appointment", "patient", "emergency",
        "If the doctor is unavailable, who can help me?", "When can I see the doctor?"),
    "wellness": ("consultation", "therapist", "session", "appointment",
        "How can I book a consultation?", "When can I get a session?"),
    "real_estate": ("property", "site visit", "agent", "listing", "visit",
        "If I cannot visit today, can you arrange another time?", "Who will arrange the site visit?"),
    "education": ("course", "class", "teacher", "trainer", "batch", "fee",
        "If I miss the class, can I attend another batch?", "When does the next batch start?"),
    "automotive": ("vehicle", "car", "service", "technician", "delivery",
        "If my vehicle is not ready today, when can I collect it?", "Who will handle my service?"),
    "retail": ("product", "stock", "order", "delivery", "refund", "bill",
        "If an item is unavailable, can you replace it?", "When will my order be delivered?"),
    "pharmacy": ("medicine", "prescription", "stock", "delivery", "pharmacist",
        "If the medicine is unavailable, what are my options?", "Whom should I contact about my prescription?"),
    "beauty_spa": ("therapist", "treatment", "appointment", "session", "slot",
        "If my preferred therapist is unavailable, who can help me?", "When can I book my treatment?"),
    "professional_services": ("consultant", "lawyer", "accountant", "manager", "department", "appointment",
        "If the assigned professional is unavailable, who will handle my enquiry?", "How will the responsible person contact me?"),
}


def iter_training_prompts() -> Iterable[tuple[str, str]]:
    for intent in INTENTS:
        for prompt in QUESTION_LIBRARY[intent]:
            yield intent, prompt


def build_training_matrix() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for intent, prompt in iter_training_prompts():
        rows.append({"type": "intent", "intent": intent, "prompt": prompt})
    for scenario in UNIVERSAL_SCENARIOS:
        rows.append({"type": "scenario", "id": scenario.id, "intent": scenario.intent,
                     "prompt": scenario.prompt, "expected": list(scenario.expected)})
    for scenario in TIME_SCENARIOS:
        rows.append({"type": "time", "id": scenario.id, "intent": scenario.intent,
                     "prompt": scenario.prompt, "expected": list(scenario.expected)})
    for industry, terms in INDUSTRY_SCENARIO_TERMS.items():
        for term in terms:
            rows.append({"type": "industry", "industry": industry, "prompt": term})
    return rows


def training_context_text() -> str:
    lines = [
        "UNIVERSAL CUSTOMER SCENARIO TRAINING:",
        "These are intent examples and behavioral tests, NOT tenant facts.",
        "TIME RULE: Every requested time must be normalized to 12/24-hour form, matched against tenant-configured business hours and booking rules, checked for live availability, and confirmed before booking.",
        "This rule applies to every hour/minute, not only 7: 12 AM, 12 PM, 1-11 AM/PM, quarter-hour/half-hour times, spoken times, and Indian-language time expressions.",
        "Always use tenant-approved knowledge, live availability, configured policy and tools.",
    ]
    for intent in INTENTS:
        lines.append(f"\n{intent}:")
        lines.extend(f"- {q}" for q in QUESTION_LIBRARY[intent])
    lines.append("\nMANDATORY BEHAVIOR SCENARIOS:")
    for s in UNIVERSAL_SCENARIOS:
        lines.append(f"- [{s.intent}] {s.prompt} => {', '.join(s.expected)}")
    lines.append("\nFULL 24-HOUR TIME SCENARIOS (1 AM-12 AM and 1 PM-12 PM):")
    for s in TIME_SCENARIOS:
        lines.append(f"- [{s.intent}] {s.prompt} => {', '.join(s.expected)}")
    return "\n".join(lines)
