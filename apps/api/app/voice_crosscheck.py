"""Real-time voice-turn cross-check for the live call runtime.

Fast, deterministic and side-effect free. It runs on each finalized customer
transcript while the realtime provider remains connected. It never replaces
the provider response; dynamic business facts still require the owned live
tools (availability/booking/payment/etc.) before being stated or committed.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter

from .knowledge_brain_v2 import classify


LIVE_DATA_INTENTS = {
    "CHECK_AVAILABILITY",
    "BOOK",
    "CHANGE_BOOKING",
    "RESCHEDULE",
    "CANCEL_BOOKING",
    "CONFIRM_BOOKING",
    "GET_BOOKING_DETAILS",
    "PAYMENT_STATUS",
    "PAYMENT_REFUND",
    "PAYMENT_PENDING",
    "ORDER_STATUS",
    "ORDER_TRACKING",
    "LOYALTY_BALANCE",
    "CURRENT_OFFERS",
    "SERVICE_AVAILABILITY",
    "PRODUCT_AVAILABILITY",
    "PRODUCT_STOCK",
}


@dataclass(frozen=True)
class VoiceCrosscheck:
    intent: str
    confidence: float
    entities: dict[str, str]
    live_data_required: bool
    latency_ms: float
    source: str = "knowledge_brain_v2_realtime"


def crosscheck_turn(message: str, industry: str | None = None) -> VoiceCrosscheck:
    started = perf_counter()
    result = classify(message, industry)
    return VoiceCrosscheck(
        intent=result.intent,
        confidence=result.confidence,
        entities=result.entities,
        live_data_required=result.intent in LIVE_DATA_INTENTS,
        latency_ms=round((perf_counter() - started) * 1000, 3),
    )


def crosscheck_payload(result: VoiceCrosscheck) -> dict:
    return asdict(result)
