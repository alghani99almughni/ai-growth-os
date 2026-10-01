"""Intent registry.

Maps intent names (as produced by the classifier) to the handler functions
that know how to answer them. The router orchestrator looks up handlers here.

Each handler has the same signature:
    async def handler(db, tenant, message, language, entities, context) -> str | None
Handlers return None to signal "I cannot answer this", letting the
orchestrator try the next layer.
"""
from __future__ import annotations

from typing import Callable, Optional

from .intent_handlers import (
    handle_business_hours as _handle_business_hours_legacy,
    handle_pricing,
    handle_location,
    handle_availability,
    handle_staff_info,
    handle_booking_status,
    handle_booking_cancel,
    handle_order_status,
    handle_delay_query,
    handle_callback_request,
    handle_human_handoff,
    handle_complaint,
    handle_policy,
    handle_refund,
    handle_emergency,
)
from .intent_handlers_hours import handle_business_hours


IntentHandler = Callable[..., object]


INTENT_HANDLERS: dict = {
    # Business hours (upgraded handler)
    "business_hours":              handle_business_hours,
    "business_hours_full":         handle_business_hours,
    "business_hours_today":        handle_business_hours,
    "business_hours_now":          handle_business_hours,
    "business_hours_next_open":    handle_business_hours,
    "business_hours_next_close":   handle_business_hours,
    "business_hours_closed_today": handle_business_hours,

    # Info
    "pricing":      handle_pricing,
    "location":     handle_location,
    "availability": handle_availability,
    "staff_info":   handle_staff_info,

    # Booking lifecycle
    "booking_status": handle_booking_status,
    "booking_cancel": handle_booking_cancel,

    # Order lifecycle
    "order_status": handle_order_status,
    "delay_query":  handle_delay_query,

    # Communication
    "callback_request": handle_callback_request,
    "human_handoff":    handle_human_handoff,

    # Sentiment / issue
    "complaint": handle_complaint,
    "refund":    handle_refund,
    "emergency": handle_emergency,

    # Policy
    "policy": handle_policy,
}


def get_handler(intent: str) -> Optional[IntentHandler]:
    return INTENT_HANDLERS.get(intent)


def all_registered_intents() -> list:
    return list(INTENT_HANDLERS.keys())


def has_handler(intent: str) -> bool:
    return intent in INTENT_HANDLERS