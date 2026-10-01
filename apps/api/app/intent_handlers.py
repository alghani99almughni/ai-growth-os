"""Intent handlers - Part 1.

One async function per intent. Each handler:
- never raises
- returns a reply string on success
- returns None if it cannot answer (orchestrator falls through)

Part 1 covers: business_hours, pricing, location, availability, staff_info.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature gate helper
# ---------------------------------------------------------------------------

def _feature_enabled(db, tenant, key, default=True):
    """Return whether a feature is enabled for this tenant.

    Reads from feature_gate.get_features which layers:
    platform defaults -> industry defaults -> platform override -> tenant override.
    """
    try:
        from .feature_gate import feature_enabled
        return feature_enabled(db, tenant.id, key, default)
    except Exception:
        # If anything fails, be permissive to avoid blocking real requests.
        return True




# ---------------------------------------------------------------------------
# AgentVoice helper. Reads gender from context, defaults to female.
# ---------------------------------------------------------------------------

def _voice_for(language: str, context: dict):
    """Return an AgentVoice bound to the caller language and the tenant's
    configured receptionist gender. Defaults to female when unset."""
    try:
        from .agent_voice import AgentVoice
    except Exception:
        return None
    gender = (context or {}).get("agent_gender", "female")
    try:
        return AgentVoice(language=language or "en", gender=gender)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _tenant_now(tenant) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(getattr(tenant, "timezone", "Asia/Kolkata")))
    except Exception:
        return datetime.utcnow()


def _fmt_time(t) -> str:
    if t is None:
        return ""
    try:
        return t.strftime("%I:%M %p").lstrip("0")
    except Exception:
        return str(t)


def _day_names() -> list:
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ---------------------------------------------------------------------------
# 1. business_hours
# ---------------------------------------------------------------------------

async def handle_business_hours(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer opening-hours questions from BusinessHour rows."""
    try:
        from .models_growth import BusinessHour
        rows = db.scalars(
            select(BusinessHour)
            .where(BusinessHour.tenant_id == tenant.id)
            .order_by(BusinessHour.weekday)
        ).all()
        if not rows:
            return None

        open_days = [r for r in rows if not r.is_closed]
        if not open_days:
            return "We are currently closed for all days."

        names = _day_names()
        # If all open days share the same hours, summarize as "Mon-Sat, X to Y".
        same_hours = all(
            r.open_time == open_days[0].open_time and r.close_time == open_days[0].close_time
            for r in open_days
        )
        weekdays = {r.weekday for r in open_days}

        if same_hours and weekdays == {0, 1, 2, 3, 4, 5}:
            opening = _fmt_time(open_days[0].open_time)
            closing = _fmt_time(open_days[0].close_time)
            if language == "hi":
                return f"हम सोमवार से शनिवार, {opening} से {closing} तक खुले रहते हैं। रविवार बंद रहता है।"
            if language == "te":
                return f"మేము సోమవారం నుండి శనివారం వరకు, {opening} నుండి {closing} వరకు తెరిచి ఉంటాము. ఆదివారం మూసి ఉంటుంది."
            if language == "ta":
                return f"நாங்கள் திங்கள் முதல் சனி வரை, {opening} முதல் {closing} வரை திறந்திருக்கிறோம். ஞாயிறு மூடப்பட்டிருக்கும்."
            return f"We're open Monday to Saturday, {opening} to {closing}. Sunday we're closed."

        # Fallback: list per day.
        parts = []
        for r in rows:
            label = names[r.weekday] if 0 <= r.weekday < len(names) else str(r.weekday)
            if r.is_closed:
                parts.append(f"{label}: closed")
            else:
                parts.append(f"{label}: {_fmt_time(r.open_time)} - {_fmt_time(r.close_time)}")
        return "Our hours are " + "; ".join(parts) + "."
    except Exception as exc:
        logger.debug("business_hours handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 2. pricing
# ---------------------------------------------------------------------------

async def handle_pricing(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer pricing questions from Service/Product rows."""
    try:
        # Prices are shown only when the tenant enabled show_pricing.
        try:
            from .feature_gate import feature_enabled as _fe
            if not _fe(db, tenant.id, "show_pricing", False):
                return None
        except Exception:
            pass
        from .models import Service, Product

        services = db.scalars(
            select(Service).where(
                Service.tenant_id == tenant.id,
                Service.is_active == True,
            )
        ).all()
        products = db.scalars(
            select(Product).where(
                Product.tenant_id == tenant.id,
                Product.is_active == True,
            )
        ).all()

        lines = []
        for s in services:
            if s.price is not None:
                lines.append(f"{s.name}: {s.currency} {s.price}")
        for p in products:
            if p.price is not None:
                lines.append(f"{p.name}: {p.currency} {p.price}")

        if not lines:
            return None

        if language == "hi":
            return "हमारी सेवाओं की कीमतें इस प्रकार हैं: " + "; ".join(lines)
        if language == "te":
            return "మా సేవల ధరలు: " + "; ".join(lines)
        if language == "ta":
            return "எங்கள் சேவை விலைகள்: " + "; ".join(lines)
        return "Here are our prices: " + "; ".join(lines)
    except Exception as exc:
        logger.debug("pricing handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 3. location
# ---------------------------------------------------------------------------

async def handle_location(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer location questions from Tenant.address."""
    try:
        address = getattr(tenant, "address", None)
        if not address:
            return None
        if language == "hi":
            return f"हमारा पता है: {address}"
        if language == "te":
            return f"మా చిరునామా: {address}"
        if language == "ta":
            return f"எங்கள் முகவரி: {address}"
        return f"We are located at: {address}"
    except Exception as exc:
        logger.debug("location handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 4. availability
# ---------------------------------------------------------------------------

async def handle_availability(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer availability questions by listing the next few slots."""
    try:
        if not _feature_enabled(db, tenant, "bookings"):
            return None
        from .booking import available_slots
        from .models import Service
        from datetime import timedelta

        service = db.scalar(
            select(Service)
            .where(Service.tenant_id == tenant.id, Service.is_active == True)
            .order_by(Service.name)
            .limit(1)
        )
        if not service:
            return None

        now_local = _tenant_now(tenant)
        # Look at today and the next 6 days.
        for offset in range(0, 7):
            day = (now_local + timedelta(days=offset)).date()
            slots = available_slots(db, tenant, service.id, day)
            if slots:
                times = [
                    datetime.fromisoformat(s["start"]).strftime("%I:%M %p").lstrip("0")
                    for s in slots[:4]
                ]
                day_label = day.strftime("%A, %B %d")
                if language == "hi":
                    return f"{day_label} को उपलब्ध समय: {', '.join(times)}। कौन सा समय चाहिए?"
                if language == "te":
                    return f"{day_label} న అందుబాటులో ఉన్న సమయాలు: {', '.join(times)}. ఏ సమయం కావాలి?"
                if language == "ta":
                    return f"{day_label} அன்று கிடைக்கும் நேரங்கள்: {', '.join(times)}. எந்த நேரம் வேண்டும்?"
                return f"{day_label} has slots at {', '.join(times)}. Which time works for you?"

        return None
    except Exception as exc:
        logger.debug("availability handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 5. staff_info
# ---------------------------------------------------------------------------

async def handle_staff_info(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer staff/doctor questions from StaffMember rows."""
    try:
        from .models_ai import StaffMember
        staff = db.scalars(
            select(StaffMember)
            .where(StaffMember.tenant_id == tenant.id, StaffMember.is_active == True)
        ).all()
        if not staff:
            return None

        names = [s.name for s in staff[:5]]
        joined = ", ".join(names)

        if language == "hi":
            return f"हमारे पास ये टीम सदस्य हैं: {joined}।"
        if language == "te":
            return f"మా బృందంలో ఉన్నవారు: {joined}."
        if language == "ta":
            return f"எங்கள் குழுவில் உள்ளவர்கள்: {joined}."
        return f"Our team includes: {joined}."
    except Exception as exc:
        logger.debug("staff_info handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 6. booking_status
# ---------------------------------------------------------------------------

async def handle_booking_status(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer questions about the customer's upcoming appointment."""
    try:
        if not _feature_enabled(db, tenant, "bookings"):
            return None
        from .models_growth import Appointment
        from sqlalchemy import desc

        customer = context.get("customer") if isinstance(context, dict) else None
        if not customer:
            return None

        upcoming = db.scalars(
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant.id,
                Appointment.customer_id == customer.id,
                Appointment.status.in_(["confirmed", "checked_in"]),
                Appointment.starts_at >= datetime.utcnow(),
            )
            .order_by(Appointment.starts_at)
            .limit(3)
        ).all()
        if not upcoming:
            if language == "hi":
                return "मेरे पास आपकी कोई आगामी अपॉइंटमेंट नहीं दिख रही।"
            if language == "te":
                return "మీకు రాబోయే అపాయింట్‌మెంట్లు ఏవీ లేవు."
            return "I don't see any upcoming appointments for you."

        first = upcoming[0]
        when = first.starts_at.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
        if language == "hi":
            return f"आपकी अगली अपॉइंटमेंट {when} पर है।"
        if language == "te":
            return f"మీ తదుపరి అపాయింట్‌మెంట్ {when} న ఉంది."
        if language == "ta":
            return f"உங்கள் அடுத்த அப்பாயிண்ட்மென்ட் {when} அன்று."
        return f"Your next appointment is on {when}."
    except Exception as exc:
        logger.debug("booking_status handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 7. booking_cancel
# ---------------------------------------------------------------------------

async def handle_booking_cancel(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Find the next upcoming appointment and mark it cancelled."""
    try:
        if not _feature_enabled(db, tenant, "bookings"):
            return None
        from .models_growth import Appointment

        customer = context.get("customer") if isinstance(context, dict) else None
        if not customer:
            return None

        upcoming = db.scalar(
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant.id,
                Appointment.customer_id == customer.id,
                Appointment.status.in_(["confirmed", "checked_in"]),
                Appointment.starts_at >= datetime.utcnow(),
            )
            .order_by(Appointment.starts_at)
            .limit(1)
        )
        if not upcoming:
            if language == "hi":
                return "मेरे पास रद्द करने के लिए कोई आगामी अपॉइंटमेंट नहीं है।"
            return "I don't see any upcoming appointment to cancel."

        upcoming.status = "cancelled"
        db.commit()

        when = upcoming.starts_at.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
        if language == "hi":
            return f"आपकी {when} की अपॉइंटमेंट रद्द कर दी गई है।"
        if language == "te":
            return f"మీ {when} అపాయింట్‌మెంట్ రద్దు చేయబడింది."
        if language == "ta":
            return f"உங்கள் {when} அப்பாயிண்ட்மென்ட் ரத்து செய்யப்பட்டது."
        return f"Your appointment on {when} has been cancelled."
    except Exception as exc:
        logger.debug("booking_cancel handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# 8. order_status
# ---------------------------------------------------------------------------

async def handle_order_status(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer questions about the customer's most recent order."""
    try:
        if not _feature_enabled(db, tenant, "online_ordering"):
            return None
        from .models_growth import Order

        customer = context.get("customer") if isinstance(context, dict) else None
        if not customer:
            return None

        order = db.scalar(
            select(Order)
            .where(
                Order.tenant_id == tenant.id,
                Order.customer_id == customer.id,
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        if not order:
            if language == "hi":
                return "मेरे पास आपकी कोई हालिया ऑर्डर नहीं मिली।"
            return "I don't see any recent orders from you."

        status = (order.status or "pending").lower()
        if language == "hi":
            return f"आपकी ऑर्डर #{str(order.id)[:8]} अभी '{status}' स्थिति में है।"
        if language == "te":
            return f"మీ ఆర్డర్ #{str(order.id)[:8]} ప్రస్తుతం '{status}' స్థితిలో ఉంది."
        if language == "ta":
            return f"உங்கள் ஆர்டர் #{str(order.id)[:8]} தற்போது '{status}' நிலையில் உள்ளது."
        return f"Your order #{str(order.id)[:8]} is currently '{status}'."
    except Exception as exc:
        logger.debug("order_status handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 9. delay_query
# ---------------------------------------------------------------------------

async def handle_delay_query(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer 'why is it late' by checking recent orders/appointments."""
    try:
        if not _feature_enabled(db, tenant, "online_ordering"):
            return None
        from .models_growth import Order, Appointment

        customer = context.get("customer") if isinstance(context, dict) else None
        if not customer:
            return None

        # Most recent active order
        order = db.scalar(
            select(Order)
            .where(
                Order.tenant_id == tenant.id,
                Order.customer_id == customer.id,
                Order.status.in_(["confirmed", "preparing", "ready"]),
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        if order:
            status = (order.status or "").lower()
            if language == "hi":
                return f"आपकी ऑर्डर अभी '{status}' पर है। टीम इसे प्राथमिकता दे रही है।"
            return f"Your order is currently '{status}'. The team is treating it as a priority."

        # Else check next appointment
        appt = db.scalar(
            select(Appointment)
            .where(
                Appointment.tenant_id == tenant.id,
                Appointment.customer_id == customer.id,
                Appointment.status.in_(["confirmed", "checked_in"]),
            )
            .order_by(Appointment.starts_at)
            .limit(1)
        )
        if appt:
            when = appt.starts_at.strftime("%A, %B %d at %I:%M %p").replace(" 0", " ")
            if language == "hi":
                return f"आपकी अपॉइंटमेंट {when} पर निर्धारित है।"
            return f"Your appointment is scheduled for {when}."

        return None
    except Exception as exc:
        logger.debug("delay_query handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 10. callback_request
# ---------------------------------------------------------------------------

async def handle_callback_request(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Create a Lead so staff can follow up with a callback."""
    try:
        from .models import Lead, Customer

        customer = context.get("customer") if isinstance(context, dict) else None
        phone = entities.get("phone")
        name = None
        customer_id = None

        if customer:
            name = customer.name
            phone = phone or customer.mobile
            customer_id = customer.id

        if not phone:
            if language == "hi":
                return "कृपया अपना मोबाइल नंबर बताएं ताकि हम कॉल कर सकें।"
            if language == "te":
                return "దయచేసి మీ మొబైల్ నంబర్ చెప్పండి."
            return "Please share your mobile number so we can call you back."

        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer_id,
            customer_name=name or "Guest",
            mobile=phone,
            intent="callback",
            source="ai_voice",
            status="new",
            notes=(message or "")[:300],
        )
        db.add(lead)
        db.commit()

        if language == "hi":
            return "हमने आपका कॉलबैक अनुरोध दर्ज कर लिया है। टीम जल्द ही कॉल करेगी।"
        if language == "te":
            return "మీ కాల్‌బ్యాక్ అభ్యర్థన నమోదు చేయబడింది. బృందం త్వరలో కాల్ చేస్తుంది."
        if language == "ta":
            voice = _voice_for(language, context)
            if voice is not None:
                return voice.render("callback_logged")
            return "I'm here to help. Please hold on a moment."
    except Exception as exc:
        logger.debug("callback_request handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None



# ---------------------------------------------------------------------------
# 11. human_handoff
# ---------------------------------------------------------------------------

async def handle_human_handoff(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Create a CallRecord so staff can pick up the conversation."""
    try:
        if not _feature_enabled(db, tenant, "human_handoff"):
            return None
        from .models_growth import CallRecord

        customer = context.get("customer") if isinstance(context, dict) else None

        record = CallRecord(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            language=language,
            intent="human_handoff",
            summary=(message or "")[:300],
            status="waiting",
        )
        db.add(record)
        db.commit()

        voice = _voice_for(language, context)
        if voice is not None:
            return voice.render("handoff_requested")
        return "I've passed this to the team. A member will join shortly."
    except Exception as exc:
        logger.debug("human_handoff handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# 12. complaint
# ---------------------------------------------------------------------------

async def handle_complaint(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Log complaint as a Lead and return an empathetic reply."""
    try:
        from .models import Lead

        customer = context.get("customer") if isinstance(context, dict) else None

        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            intent="complaint",
            source="ai_voice",
            status="new",
            notes=(message or "")[:500],
        )
        db.add(lead)
        db.commit()

        voice = _voice_for(language, context)
        if voice is not None:
            return voice.render("complaint_received")
        return "I'm sorry you had that experience. I've shared this with the team and they'll reach out shortly."
    except Exception as exc:
        logger.debug("complaint handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# 13. policy
# ---------------------------------------------------------------------------

async def handle_policy(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer policy questions from the tenant knowledge library."""
    try:
        from .ai_router import knowledge_match

        answer = knowledge_match(db, tenant.id, message)
        if answer:
            return answer
        return None
    except Exception as exc:
        logger.debug("policy handler failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# 14. refund
# ---------------------------------------------------------------------------

async def handle_refund(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Try tenant knowledge library for refund policy; else log a Lead."""
    try:
        from .ai_router import knowledge_match

        answer = knowledge_match(db, tenant.id, message)
        if answer:
            return answer

        from .models import Lead
        customer = context.get("customer") if isinstance(context, dict) else None
        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            intent="refund",
            source="ai_voice",
            status="new",
            notes=(message or "")[:300],
        )
        db.add(lead)
        db.commit()

        voice = _voice_for(language, context)
        if voice is not None:
            return voice.render("refund_forwarded")
        return "I've passed this to the team to confirm the refund policy. They'll reach out shortly."
    except Exception as exc:
        logger.debug("refund handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# 15. emergency
# ---------------------------------------------------------------------------

async def handle_emergency(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Log an urgent Lead and CallRecord so staff is alerted immediately."""
    try:
        from .models import Lead
        from .models_growth import CallRecord

        customer = context.get("customer") if isinstance(context, dict) else None

        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            intent="emergency",
            source="ai_voice",
            status="new",
            notes=(message or "")[:500],
        )
        db.add(lead)

        call = CallRecord(
            tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            customer_name=(customer.name if customer else "Guest") or "Guest",
            mobile=(customer.mobile if customer else "") or "",
            language=language,
            intent="emergency",
            summary="URGENT: " + (message or "")[:280],
            status="waiting",
        )
        db.add(call)
        db.commit()

        voice = _voice_for(language, context)
        if voice is not None:
            return voice.render("emergency_flagged")
        return "I've flagged this as urgent. The team will reach out immediately."
    except Exception as exc:
        logger.debug("emergency handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None

