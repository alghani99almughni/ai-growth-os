"""Global Knowledge Brain taxonomy layered over the legacy tenant Knowledge Library.

This module is intentionally non-destructive: it classifies a turn into a canonical
intent for analytics, retrieval planning and future industry packs. It does not
replace brain.py, tenant KnowledgeItem records, GlobalFaq, or action handlers.
"""
from __future__ import annotations

import re
from typing import Optional

CORE_INTENTS = {
    "DISCOVER_BUSINESS", "DISCOVER_SERVICES", "DISCOVER_PRODUCTS", "DISCOVER_SPECIALTIES",
    "GET_HOURS", "GET_TODAY_HOURS", "GET_TOMORROW_HOURS", "GET_SPECIAL_HOURS",
    "GET_LOCATION", "GET_DIRECTIONS", "GET_DISTANCE", "GET_PARKING", "GET_CONTACT", "GET_WHATSAPP",
    "LIST_SERVICES", "SERVICE_DETAILS", "SERVICE_PRICE", "SERVICE_DURATION",
    "SERVICE_INCLUSIONS", "SERVICE_AVAILABILITY", "SERVICE_PROVIDER", "SERVICE_PACKAGE",
    "SERVICE_COMPARISON", "LIST_PRODUCTS", "PRODUCT_DETAILS", "PRODUCT_PRICE",
    "PRODUCT_AVAILABILITY", "PRODUCT_STOCK", "PRODUCT_VARIANT", "PRODUCT_USAGE",
    "GET_PRICE", "GET_FEES", "GET_TAX", "GET_DISCOUNT", "GET_PACKAGE_PRICE",
    "GET_PAYMENT_TERMS", "GET_CANCELLATION_FEE", "GET_REFUND_POLICY",
    "BOOK", "CHECK_AVAILABILITY", "CHANGE_BOOKING", "RESCHEDULE", "CANCEL_BOOKING",
    "CONFIRM_BOOKING", "GET_BOOKING_DETAILS", "REJECT", "CANCEL", "CORRECT", "CHANGE",
    "ACKNOWLEDGEMENT", "VOICE_FEEDBACK", "REPEAT_REQUEST", "CLARIFICATION_REQUEST",
    "PAYMENT_METHODS", "PAYMENT_LINK", "PAYMENT_STATUS", "PAYMENT_FAILED",
    "PAYMENT_PENDING", "PAYMENT_REFUND", "PAYMENT_RECEIPT", "PAYMENT_INVOICE",
    "CURRENT_OFFERS", "DISCOUNTS", "COUPONS", "LOYALTY_BALANCE", "EARN_POINTS",
    "REDEEM_POINTS", "CREATE_ACCOUNT", "UPDATE_PROFILE", "LOGIN", "PASSWORD_RESET",
    "PLACE_ORDER", "ORDER_STATUS", "ORDER_TRACKING", "CHANGE_ORDER", "CANCEL_ORDER",
    "RETURN_POLICY", "RETURN_REQUEST", "REFUND_POLICY", "REFUND_STATUS", "EXCHANGE",
    "DELIVERY_AREA", "DELIVERY_TIME", "SHIPPING_COST", "TRACK_DELIVERY",
    "TECHNICAL_SUPPORT", "COMPLAINT", "POOR_SERVICE", "BILLING_COMPLAINT",
    "REQUEST_HUMAN", "SPECIALIST_REQUIRED", "LOW_CONFIDENCE", "CUSTOMER_REQUESTED_CALL",
    "DOCTOR_INFORMATION", "CHECK_IN_POLICY", "CHECK_OUT_POLICY", "MENU", "ITEM_PRICE", "ITEM_AVAILABILITY", "INGREDIENTS", "ALLERGENS", "TABLE_RESERVATION", "TAKEAWAY", "DELIVERY", "MEMBERSHIP", "CLASS_SCHEDULE", "TRAINER_INFORMATION", "MEMBERSHIP_RENEWAL", "COURSE_INFORMATION", "ENROLMENT", "PROPERTY_LISTING", "PROPERTY_DETAILS", "SITE_VISIT", "RENTAL_ENQUIRY", "ROOM_AVAILABILITY", "ROOM_RESERVATION", "WARRANTY", "SALON_SERVICES", "UNKNOWN",
}

INDUSTRY_INTENTS = {
    "clinic": {"DOCTOR_INFORMATION", "SPECIALTY", "CONSULTATION", "LAB", "FOLLOW_UP", "INSURANCE", "EMERGENCY_ROUTING"},
    "healthcare": {"DOCTOR_INFORMATION", "SPECIALTY", "CONSULTATION", "LAB", "FOLLOW_UP", "INSURANCE", "EMERGENCY_ROUTING"},
    "restaurant": {"MENU", "ITEM_PRICE", "ITEM_AVAILABILITY", "INGREDIENTS", "ALLERGENS", "TABLE_RESERVATION", "TAKEAWAY", "DELIVERY"},
    "salon": {"SALON_SERVICES", "SERVICE_PROVIDER", "SERVICE_PRICE", "SERVICE_AVAILABILITY"},
    "gym": {"MEMBERSHIP", "CLASS_SCHEDULE", "TRAINER_INFORMATION", "MEMBERSHIP_RENEWAL"},
    "education": {"COURSE_INFORMATION", "ENROLMENT", "CLASS_SCHEDULE", "FEES"},
    "real_estate": {"PROPERTY_LISTING", "PROPERTY_DETAILS", "SITE_VISIT", "RENTAL_ENQUIRY"},
    "hotel": {"ROOM_AVAILABILITY", "CHECK_IN_POLICY", "CHECK_OUT_POLICY", "ROOM_RESERVATION"},
    "retail": {"PRODUCT_STOCK", "PRODUCT_VARIANT", "SHIPPING_COST", "RETURN_POLICY", "WARRANTY"},
}

LEGACY_TO_CANONICAL = {
    "business_hours": "GET_HOURS",
    "business_hours_full": "GET_HOURS",
    "business_hours_today": "GET_TODAY_HOURS",
    "business_hours_now": "GET_HOURS",
    "business_hours_next_open": "GET_SPECIAL_HOURS",
    "business_hours_next_close": "GET_SPECIAL_HOURS",
    "pricing": "GET_PRICE",
    "location": "GET_LOCATION",
    "availability": "CHECK_AVAILABILITY",
    "booking": "BOOK",
    "booking_status": "GET_BOOKING_DETAILS",
    "booking_cancel": "CANCEL_BOOKING",
    "human_handoff": "REQUEST_HUMAN",
    "callback_request": "CUSTOMER_REQUESTED_CALL",
    "voice_feedback": "VOICE_FEEDBACK",
    "clarification": "CLARIFICATION_REQUEST",
    "complaint": "COMPLAINT",
    "refund": "REFUND_POLICY",
    "product": "DISCOVER_PRODUCTS",
    "doctor_information": "DOCTOR_INFORMATION",
    "date_information": "GET_TOMORROW_HOURS",
    "closing": "ACKNOWLEDGEMENT",
}

_RULES = (
    (r"\b(?:repeat|say that again|what did you say)\b", "REPEAT_REQUEST"),
    (r"\b(?:can you hear me|audio|voice is not clear|speak louder)\b", "VOICE_FEEDBACK"),
    (r"\b(?:speak to|talk to|connect me|human|manager|representative)\b", "REQUEST_HUMAN"),
    (r"\b(?:refund policy|refund|money back)\b", "REFUND_POLICY"),
    (r"\b(?:track|where is)\b.{0,24}\b(?:order|delivery|package)\b", "ORDER_TRACKING"),
    (r"\b(?:payment status|did you receive my payment|payment failed)\b", "PAYMENT_STATUS"),
    (r"\b(?:offer|discount|coupon|promotion)\b", "CURRENT_OFFERS"),
    (r"\b(?:loyalty points|reward points|redeem points)\b", "LOYALTY_BALANCE"),
    (r"\b(?:menu|dishes|food items)\b", "MENU"),
    (r"\b(?:check in|check-in)\b", "CHECK_IN_POLICY"),
    (r"\b(?:check out|check-out)\b", "CHECK_OUT_POLICY"),
    (r"\b(?:course|classes|enrol|enroll)\b", "COURSE_INFORMATION"),
    (r"\b(?:property|flat|house|site visit)\b", "PROPERTY_LISTING"),
    (r"\b(?:membership|trainer|gym)\b", "MEMBERSHIP"),
)

def canonical_intent(message: str, legacy_intent: Optional[str] = None, industry: Optional[str] = None) -> str:
    """Return a canonical taxonomy label without changing legacy runtime routing."""
    if legacy_intent and legacy_intent in LEGACY_TO_CANONICAL:
        return LEGACY_TO_CANONICAL[legacy_intent]
    value = " ".join((message or "").casefold().split())
    for pattern, intent in _RULES:
        if re.search(pattern, value, flags=re.IGNORECASE):
            return intent
    if re.search(r"\b(?:price|cost|fee|how much)\b", value):
        return "GET_PRICE"
    if re.search(r"\b(?:book|booking|appointment|reserve)\b", value):
        return "BOOK"
    if re.search(r"\b(?:open|close|hours|timing)\b", value):
        return "GET_HOURS"
    if industry:
        pack = INDUSTRY_INTENTS.get(industry.casefold().replace(" ", "_"), set())
        for candidate in sorted(pack, key=len, reverse=True):
            words = candidate.casefold().replace("_", " ")
            if words in value:
                return candidate
    return "UNKNOWN"
