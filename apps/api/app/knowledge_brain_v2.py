"""Knowledge Brain V2: additive, provider-independent intent/entity taxonomy.

This module is intentionally side-effect free. It does not replace the existing
brain/router/booking flow. Callers can use classify() in shadow mode first and
only switch routing after regression tests prove parity.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field

UNIVERSAL_INTENTS = {
    "DISCOVER_BUSINESS","DISCOVER_SERVICES","DISCOVER_PRODUCTS","DISCOVER_SPECIALTIES",
    "GET_HOURS","GET_TODAY_HOURS","GET_TOMORROW_HOURS","GET_SPECIAL_HOURS",
    "GET_LOCATION","GET_DIRECTIONS","GET_DISTANCE","GET_PARKING","GET_CONTACT","GET_WHATSAPP",
    "LIST_SERVICES","SERVICE_DETAILS","SERVICE_PRICE","SERVICE_DURATION","SERVICE_INCLUSIONS",
    "SERVICE_AVAILABILITY","SERVICE_PROVIDER","SERVICE_PACKAGE","SERVICE_COMPARISON",
    "LIST_PRODUCTS","PRODUCT_DETAILS","PRODUCT_PRICE","PRODUCT_AVAILABILITY","PRODUCT_STOCK",
    "PRODUCT_VARIANT","PRODUCT_SIZE","PRODUCT_COLOR","PRODUCT_USAGE","PRODUCT_COMPARISON",
    "PRODUCT_RECOMMENDATION","GET_PRICE","GET_FEES","GET_TAX","GET_DISCOUNT","GET_PACKAGE_PRICE",
    "GET_PAYMENT_TERMS","GET_CANCELLATION_FEE","BOOK","CHECK_AVAILABILITY","CHANGE_BOOKING",
    "RESCHEDULE","CANCEL_BOOKING","CONFIRM_BOOKING","GET_BOOKING_DETAILS",
    "PAYMENT_METHODS","PAYMENT_LINK","PAYMENT_STATUS","PAYMENT_FAILED","PAYMENT_PENDING",
    "PAYMENT_REFUND","PAYMENT_RECEIPT","PAYMENT_INVOICE","PAYMENT_INSTALLMENTS",
    "CURRENT_OFFERS","DISCOUNTS","COUPONS","PROMOTIONS","PACKAGE_DEALS","FIRST_VISIT_OFFER",
    "SEASONAL_OFFER","LOYALTY_BALANCE","EARN_POINTS","REDEEM_POINTS","LOYALTY_RULES",
    "LOYALTY_EXPIRY","LOYALTY_REWARDS","CREATE_ACCOUNT","UPDATE_PROFILE","CHANGE_PHONE",
    "CHANGE_EMAIL","LOGIN","PASSWORD_RESET","ACCOUNT_STATUS","DELETE_ACCOUNT",
    "PLACE_ORDER","ORDER_STATUS","ORDER_TRACKING","CHANGE_ORDER","CANCEL_ORDER","ORDER_DELAY",
    "MISSING_ITEM","WRONG_ITEM","DAMAGED_ITEM","DELIVERY_AREA","DELIVERY_TIME",
    "CHANGE_ADDRESS","FAILED_DELIVERY","RETURN_POLICY","RETURN_REQUEST","REFUND_POLICY",
    "REFUND_STATUS","EXCHANGE","WARRANTY","HOW_TO","SETUP","LOGIN_PROBLEM","PASSWORD",
    "INTEGRATION","ERROR","BUG","PERFORMANCE","COMPATIBILITY","FEATURE_REQUEST",
    "COMPLAINT","POOR_SERVICE","DELAY","WRONG_INFORMATION","BILLING_COMPLAINT",
    "STAFF_COMPLAINT","PRODUCT_COMPLAINT","ESCALATION_REQUEST","REQUEST_HUMAN",
    "COMPLAINT_ESCALATION","SPECIALIST_REQUIRED","SENSITIVE_CASE","LOW_CONFIDENCE",
    "REPEATED_FAILURE","CUSTOMER_REQUESTED_CALL","CALLBACK","UNKNOWN","ACKNOWLEDGEMENT",
    "VOICE_FEEDBACK","REPEAT_REQUEST","CLARIFICATION_REQUEST","REJECT","CANCEL","CORRECT",
    "CHANGE","DECLINE",
}

INDUSTRY_INTENTS = {
    "restaurant": {"MENU","ITEM_PRICE","ITEM_AVAILABILITY","INGREDIENTS","ALLERGENS",
                   "TABLE_RESERVATION","TABLE_AVAILABILITY","TAKEAWAY","DELIVERY","ORDER",
                   "SPECIAL_REQUEST","PARKING","SEATING","EVENTS","OFFERS"},
    "clinic": {"DOCTOR_INFORMATION","SPECIALTY","CONSULTATION","APPOINTMENT","AVAILABILITY",
               "FEES","LOCATION","LAB","PRESCRIPTION_PROCESS","FOLLOW_UP","INSURANCE",
               "EMERGENCY_ROUTING"},
    "salon": {"SERVICES","SERVICE_PRICE","SERVICE_DURATION","STYLIST","STYLIST_AVAILABILITY",
              "APPOINTMENT","PACKAGE","OFFER","CANCELLATION","RESCHEDULE"},
    "spa": {"SERVICES","SERVICE_PRICE","SERVICE_DURATION","THERAPIST","THERAPIST_AVAILABILITY",
            "APPOINTMENT","PACKAGE","OFFER","CANCELLATION","RESCHEDULE"},
    "gym": {"MEMBERSHIP","MEMBERSHIP_PRICE","TRIAL","CLASS_SCHEDULE","TRAINER",
            "TRAINER_AVAILABILITY","PERSONAL_TRAINING","FACILITIES","TIMINGS",
            "CANCELLATION","RENEWAL"},
    "education": {"COURSES","FEES","ADMISSION","ELIGIBILITY","BATCH_TIMINGS","FACULTY",
                  "CLASS_SCHEDULE","LOCATION","ONLINE_CLASS","OFFLINE_CLASS","EXAM",
                  "CERTIFICATE","DEMO_CLASS"},
    "real_estate": {"PROPERTY","PRICE","LOCATION","AVAILABILITY","PROPERTY_TYPE","SIZE",
                    "AMENITIES","FLOOR_PLAN","VISIT","AGENT","LOAN","POSSESSION",
                    "LEGAL_DOCUMENTS"},
    "retail": {"PRODUCT","PRICE","STOCK","SIZE","COLOR","DELIVERY","ORDER","TRACKING",
               "RETURN","REFUND","EXCHANGE","WARRANTY","PAYMENT","DISCOUNT"},
    "ecommerce": {"PRODUCT","PRICE","STOCK","SIZE","COLOR","DELIVERY","ORDER","TRACKING",
                  "RETURN","REFUND","EXCHANGE","WARRANTY","PAYMENT","DISCOUNT"},
    "hospitality": {"ROOM_AVAILABILITY","ROOM_PRICE","BOOKING","CHECK_IN","CHECK_OUT",
                    "CANCELLATION","AMENITIES","LOCATION","TRANSPORT","FOOD","LOYALTY",
                    "UPGRADE","SPECIAL_REQUEST"},
    "professional_services": {"SERVICE","PRICE","CONSULTATION","AVAILABILITY","EXPERTISE",
                              "DOCUMENTS_REQUIRED","PROCESS","TIMELINE","LOCATION",
                              "APPOINTMENT","PAYMENT","FOLLOW_UP"},
}

ENTITY_NAMES = {
    "customer","service","product","staff","department","date","time","duration",
    "location","price","quantity","booking_id","order_id","payment_id","language",
}

# High-confidence lexical aliases. These are deliberately conservative so the
# existing router remains authoritative until V2 is explicitly enabled.
INTENT_ALIASES = {
    "GET_HOURS": ("hours","timing","timings","opening time","closing time","open today"),
    "GET_LOCATION": ("address","location","where are you","where is your"),
    "GET_CONTACT": ("phone number","contact number","contact details"),
    "GET_WHATSAPP": ("whatsapp number","whatsapp"),
    "SERVICE_PRICE": ("service price","service cost","service fee","how much is the service"),
    "PRODUCT_PRICE": ("product price","product cost","how much is the product"),
    "CHECK_AVAILABILITY": ("check availability","available slot","any slot","free slot"),
    "BOOK": ("book","booking","appointment","schedule","reserve","reservation"),
    "RESCHEDULE": ("reschedule","change my appointment time"),
    "CANCEL_BOOKING": ("cancel my booking","cancel appointment","cancel reservation"),
    "CONFIRM_BOOKING": ("confirm my booking","confirm appointment"),
    "PAYMENT_METHODS": ("payment methods","how can i pay","do you accept"),
    "PAYMENT_STATUS": ("payment status","did my payment go through"),
    "CURRENT_OFFERS": ("current offer","offers","promotion","promotions","discount"),
    "LOYALTY_BALANCE": ("loyalty balance","points balance","how many points"),
    "REQUEST_HUMAN": ("talk to a human","real person","live agent","customer support"),
    "CALLBACK": ("call me back","callback","call back"),
    "VOICE_FEEDBACK": ("can you hear me","can't hear you","audio is not clear","voice is not clear"),
    "ACKNOWLEDGEMENT": ("ok","okay","alright","sure","yes","thanks","thank you","got it"),
    "CLARIFICATION_REQUEST": ("what do you mean","can you clarify","please clarify"),
}

@dataclass(frozen=True)
class BrainV2Result:
    intent: str
    confidence: float
    entities: dict[str, str] = field(default_factory=dict)
    source: str = "v2_shadow"
    matched_alias: str | None = None

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s']+", " ", (text or "").casefold(), flags=re.UNICODE)).strip()

def extract_entities(text: str) -> dict[str, str]:
    value = _norm(text)
    result: dict[str, str] = {}
    phone = re.search(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)", value)
    if phone:
        result["customer_phone"] = phone.group(0).replace(" ", "").replace("-", "")
    date_match = re.search(r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", value)
    if date_match:
        result["date"] = date_match.group(1)
    time_match = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(a\.?m\.?|p\.?m\.?)\b", value)
    if time_match:
        result["time"] = time_match.group(0)
    return result

def classify(text: str, industry: str | None = None) -> BrainV2Result:
    value = _norm(text)
    if not value:
        return BrainV2Result("UNKNOWN", 0.0, source="v2_shadow")
    best_intent, best_alias = None, None
    best_score = 0.0
    for intent, aliases in INTENT_ALIASES.items():
        for alias in aliases:
            a = _norm(alias)
            if value == a:
                score = 1.0
            elif a in value:
                score = 0.92
            else:
                continue
            if score > best_score:
                best_intent, best_alias, best_score = intent, alias, score
    if best_intent is None:
        return BrainV2Result("UNKNOWN", 0.0, extract_entities(text), source="v2_shadow")
    return BrainV2Result(best_intent, best_score, extract_entities(text), source="v2_shadow", matched_alias=best_alias)

def industry_intents(industry: str | None) -> set[str]:
    if not industry:
        return set()
    key = industry.casefold().replace(" ", "_").replace("-", "_")
    return INDUSTRY_INTENTS.get(key, set())
