"""Append 5 more intent handlers to intent_handlers.py (Part 2)."""

import pathlib

path = pathlib.Path("intent_handlers.py")
text = path.read_text(encoding="utf-8")

NEW_HANDLERS = '''

# ---------------------------------------------------------------------------
# 6. booking_status
# ---------------------------------------------------------------------------

async def handle_booking_status(db: Session, tenant, message: str, language: str, entities: dict, context: dict) -> Optional[str]:
    """Answer questions about the customer's upcoming appointment."""
    try:
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
            return "உங்கள் கால்-பேக் கோரிக்கை பதிவு செய்யப்பட்டது. குழு விரைவில் அழைக்கும்."
        return "I've logged your callback request. The team will call you back shortly."
    except Exception as exc:
        logger.debug("callback_request handler failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None
'''

# Append before the last line of the file
if "handle_booking_status" in text:
    print("SKIP: Part 2 already present")
else:
    text = text.rstrip() + "\n" + NEW_HANDLERS + "\n"
    path.write_text(text, encoding="utf-8")
    print("OK: Part 2 appended")
    print("New file size:", len(text), "bytes")