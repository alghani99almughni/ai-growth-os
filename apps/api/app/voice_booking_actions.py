"""Safe voice-driven appointment cancellation and rescheduling.

This module is called by the public voice-turn endpoint after it resolves the
call-bound customer and conversation. It never mutates an appointment until the
customer explicitly confirms the exact action and target.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .models import Customer, Service, Tenant
from .models_ai import Conversation, InteractionEvent
from .models_growth import Appointment, BusinessHour, CallRecord, QueueEntry
from .booking import local_to_utc_naive
from .brain import extract_booking_entities, resolve_booking_date
from .events import publish_event_sync

log = logging.getLogger(__name__)
ACTIVE_STATUSES = ("requested", "confirmed", "checked_in", "serving")


def _normalize_confirmation(text: str) -> str:
    value = "".join(ch for ch in (text or "").casefold()
                    if not unicodedata.category(ch).startswith("P"))
    return " ".join(value.strip().split())


def _affirmative(text: str) -> bool:
    value = _normalize_confirmation(text)
    return value in {
        "yes", "yes please", "yeah", "yep", "sure", "confirm", "confirmed",
        "okay", "ok", "please do", "go ahead", "haan", "han", "ji", "theek hai",
        "हाँ", "हां", "जी", "అవును", "సరే", "అవును చేయండి", "ஆம்", "சரி",
        "ಹೌದು", "ಸರಿ", "അതെ", "ശരി",
    }


def _negative(text: str) -> bool:
    value = _normalize_confirmation(text)
    return value in {
        "no", "no thanks", "don't", "do not", "cancel that", "leave it",
        "not now", "no please", "nahi", "nahin", "नहीं", "मत करो",
        "వద్దు", "కాదు", "இல்லை", "வேண்டாம்", "ಬೇಡ", "ಇಲ್ಲ",
    }


def _action_intent(text: str) -> str | None:
    value = (text or "").casefold()
    cancel = re.search(
        r"\b(cancel|cancell?ation|call off|drop)\b|रद्द|రద్దు|ரத்து|ರದ್ದು|റദ്ദാക്ക",
        value,
    )
    reschedule = re.search(
        r"\b(reschedul\w*|change (?:my |the )?(?:appointment|booking|time|timing|date)|"
        r"change (?:the )?(?:time|timing|date)|move (?:my |the )?(?:appointment|booking)|"
        r"move it to|shift (?:my |the )?(?:appointment|booking)|shift it|"
        r"change it to|make it (?:at|on))\b"
        r"|समय बदल|तारीख बदल|समय बदलना|तारीख बदलना|మార్చు|తేదీ మార్చ|సమయం మార్చ|"
        r"நேரம் மாற்ற|தேதி மாற்ற|நேரத்தை மாற்ற|ಸಮಯ ಬದಲ|ದಿನಾಂಕ ಬದಲ|സമയം മാറ്റ|തീയതി മാറ്റ",
        value,
    )
    if reschedule:
        return "reschedule"
    if cancel:
        return "cancel"
    return None


def _upcoming(db, tenant_id: str, customer_id: str):
    return db.scalars(
        select(Appointment).where(
            Appointment.tenant_id == tenant_id,
            Appointment.customer_id == customer_id,
            Appointment.starts_at >= datetime.utcnow(),
            Appointment.status.in_(ACTIVE_STATUSES),
        ).order_by(Appointment.starts_at.asc())
    ).all()


def _when(appointment: Appointment, tenant: Tenant) -> str:
    # Appointment timestamps are stored as naive UTC; speak the tenant-local time.
    local = appointment.starts_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(tenant.timezone))
    return local.strftime("%A, %B %-d at %-I:%M %p")


def _event(db, tenant: Tenant, call: CallRecord, appointment: Appointment,
           event_type: str, before: dict, after: dict, request_text: str):
    payload = {
        "appointment_id": appointment.id,
        "customer_id": appointment.customer_id,
        "service_id": appointment.service_id,
        "call_id": call.id,
        "source": "ai_voice",
        "request_text": (request_text or "")[:1000],
        "before": before,
        "after": after,
        "recorded_at": datetime.utcnow().isoformat() + "Z",
    }
    db.add(InteractionEvent(
        tenant_id=tenant.id,
        customer_id=appointment.customer_id,
        call_id=call.id,
        channel="voice",
        event_type=event_type,
        payload_json=json.dumps(payload, ensure_ascii=False),
    ))


def _notify(tenant: Tenant, call: CallRecord, appointment: Appointment,
            event_name: str, message: str):
    try:
        publish_event_sync(tenant.id, event_name, {
            "appointment_id": appointment.id,
            "customer_id": appointment.customer_id,
            "call_id": call.id,
            "status": appointment.status,
            "starts_at": appointment.starts_at.isoformat(),
            "message": message,
            "source": "ai_voice",
        })
    except Exception:
        log.exception("VOICE_APPOINTMENT_EVENT_PUBLISH_FAILED tenant_id=%s appointment_id=%s",
                      tenant.id, appointment.id)


def _parse_new_start(tenant: Tenant, text: str):
    entities = extract_booking_entities(text)
    target_date = resolve_booking_date(
        tenant, entities.get("day"), entities.get("relative_day"), entities.get("date_hint")
    )
    raw_time = str(entities.get("time") or "").strip().upper().replace(".", "")
    # A time without an AM/PM marker is ambiguous; never guess morning/evening.
    if not target_date or not re.search(r"\b(?:AM|PM)\b", raw_time):
        return None
    match = re.fullmatch(r"(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(AM|PM)", raw_time)
    if not match:
        return None
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3) == "PM":
        hour += 12
    return datetime.combine(target_date, dt_time(hour, minute))


def handle_voice_appointment_action(db, tenant: Tenant, call: CallRecord,
                                    conversation: Conversation | None,
                                    message: str, prior_state: str) -> dict | None:
    """Return an override response when an appointment action is in progress."""
    if not call or not call.customer_id:
        if _action_intent(message):
            return {"reply": "Before I change an appointment, I need to verify your name and mobile number.",
                    "appointment_action": {"status": "identity_required"}}
        return None
    customer = db.get(Customer, call.customer_id)
    if not customer:
        return {"reply": "I couldn't verify the customer record, so I haven't changed any appointment.",
                "appointment_action": {"status": "identity_error"}}

    state = prior_state or ""
    action_match = re.fullmatch(r"voice_action:(cancel_confirm|reschedule_wait|reschedule_confirm):([^:]+)(?::(.+))?", state)
    if action_match:
        step, appointment_id, requested_iso = action_match.groups()
        appointment = db.scalar(select(Appointment).where(
            Appointment.id == appointment_id,
            Appointment.tenant_id == tenant.id,
            Appointment.customer_id == customer.id,
        ))
        if not appointment or appointment.status not in ACTIVE_STATUSES:
            if conversation:
                conversation.state = "information"
            return {"reply": "I couldn't find that active appointment, so no change was made.",
                    "appointment_action": {"status": "not_found"}}

        if step == "cancel_confirm":
            if _negative(message):
                if conversation:
                    conversation.state = "information"
                return {"reply": "No problem. I've left your appointment unchanged.",
                        "appointment_action": {"status": "unchanged", "appointment_id": appointment.id}}
            if not _affirmative(message):
                return {"reply": f"Please say yes to cancel the appointment on {_when(appointment, tenant)}, or no to keep it.",
                        "appointment_action": {"status": "awaiting_confirmation", "appointment_id": appointment.id}}
            before = {"status": appointment.status, "starts_at": appointment.starts_at.isoformat(),
                      "ends_at": appointment.ends_at.isoformat()}
            appointment.status = "cancelled"
            queue = db.scalar(select(QueueEntry).where(QueueEntry.appointment_id == appointment.id))
            if queue:
                queue.status = "cancelled"
                queue.completed_at = datetime.utcnow()
                appointment.queue_status = "cancelled"
            _event(db, tenant, call, appointment, "appointment_cancelled", before,
                   {"status": "cancelled", "starts_at": appointment.starts_at.isoformat()},
                   message)
            call.intent = "appointment_cancellation"
            call.resolution = "appointment_cancelled"
            call.summary = f"Appointment cancelled: appointment_id={appointment.id}; call_id={call.id}"
            if conversation:
                conversation.state = "information"
            db.commit()
            _notify(tenant, call, appointment, "appointment.cancelled",
                    f"Appointment cancelled: {_when(appointment, tenant)}")
            return {"reply": f"Your appointment for {_when(appointment, tenant)} has been cancelled successfully.",
                    "appointment_action": {"status": "cancelled", "appointment_id": appointment.id}}

        if step == "reschedule_wait":
            requested = _parse_new_start(tenant, message)
            if not requested:
                return {"reply": "What new date and time would you prefer? Please include AM or PM, for example Monday at 11 AM.",
                        "appointment_action": {"status": "awaiting_new_time", "appointment_id": appointment.id}}
            duration = appointment.ends_at - appointment.starts_at
            requested_end = requested + duration
            # Tenant-local hours must permit the requested slot.
            hours = db.scalar(select(BusinessHour).where(
                BusinessHour.tenant_id == tenant.id,
                BusinessHour.weekday == requested.weekday(),
            ))
            if hours and (hours.is_closed or requested.time() < hours.open_time or requested_end.time() > hours.close_time):
                return {"reply": "That time is outside the business's available hours. What other date and time would you prefer?",
                        "appointment_action": {"status": "slot_unavailable", "appointment_id": appointment.id}}
            requested_utc = local_to_utc_naive(requested, tenant.timezone)
            requested_end_utc = local_to_utc_naive(requested_end, tenant.timezone)
            conflict = db.scalar(select(Appointment).where(
                Appointment.tenant_id == tenant.id,
                Appointment.id != appointment.id,
                Appointment.starts_at < requested_end_utc,
                Appointment.ends_at > requested_utc,
                Appointment.status.in_(ACTIVE_STATUSES),
            ).limit(1))
            if conflict:
                return {"reply": "That time is no longer available. Please choose another date and time.",
                        "appointment_action": {"status": "slot_unavailable", "appointment_id": appointment.id}}
            if conversation:
                conversation.state = f"voice_action:reschedule_confirm:{appointment.id}:{requested.isoformat()}"
            return {"reply": f"I can move your appointment from {_when(appointment, tenant)} to {requested.strftime('%A, %B %-d at %-I:%M %p')}. Shall I confirm that change?",
                    "appointment_action": {"status": "awaiting_confirmation", "appointment_id": appointment.id,
                                           "requested_starts_at": requested.isoformat()}}

        if step == "reschedule_confirm":
            if _negative(message):
                if conversation:
                    conversation.state = "information"
                return {"reply": "No problem. I've left your original appointment unchanged.",
                        "appointment_action": {"status": "unchanged", "appointment_id": appointment.id}}
            if not _affirmative(message):
                return {"reply": "Please say yes to confirm the new time, or no to keep your original appointment.",
                        "appointment_action": {"status": "awaiting_confirmation", "appointment_id": appointment.id}}
            try:
                requested = datetime.fromisoformat(requested_iso)
            except (TypeError, ValueError):
                if conversation:
                    conversation.state = "information"
                return {"reply": "I couldn't verify the requested time. Your original appointment is unchanged.",
                        "appointment_action": {"status": "invalid_time", "appointment_id": appointment.id}}
            duration = appointment.ends_at - appointment.starts_at
            requested_end = requested + duration
            requested_utc = local_to_utc_naive(requested, tenant.timezone)
            requested_end_utc = local_to_utc_naive(requested_end, tenant.timezone)
            conflict = db.scalar(select(Appointment).where(
                Appointment.tenant_id == tenant.id,
                Appointment.id != appointment.id,
                Appointment.starts_at < requested_end_utc,
                Appointment.ends_at > requested_utc,
                Appointment.status.in_(ACTIVE_STATUSES),
            ).limit(1))
            if conflict:
                if conversation:
                    conversation.state = f"voice_action:reschedule_wait:{appointment.id}"
                return {"reply": "That slot was taken while we were confirming. Please choose another date and time.",
                        "appointment_action": {"status": "slot_unavailable", "appointment_id": appointment.id}}
            before = {"status": appointment.status, "starts_at": appointment.starts_at.isoformat(),
                      "ends_at": appointment.ends_at.isoformat()}
            appointment.starts_at = requested_utc
            appointment.ends_at = requested_end_utc
            appointment.status = "confirmed"
            _event(db, tenant, call, appointment, "appointment_rescheduled", before,
                   {"status": appointment.status, "starts_at": appointment.starts_at.isoformat(),
                    "ends_at": appointment.ends_at.isoformat()}, message)
            call.intent = "appointment_rescheduling"
            call.resolution = "appointment_rescheduled"
            call.summary = f"Appointment rescheduled: appointment_id={appointment.id}; call_id={call.id}"
            if conversation:
                conversation.state = "information"
            db.commit()
            _notify(tenant, call, appointment, "appointment.rescheduled",
                    f"Appointment rescheduled to {_when(appointment, tenant)}")
            return {"reply": f"Your appointment has been rescheduled to {_when(appointment, tenant)}.",
                    "appointment_action": {"status": "rescheduled", "appointment_id": appointment.id,
                                           "starts_at": appointment.starts_at.isoformat()}}

    # If the customer is choosing among multiple appointments, resolve only an explicit choice.
    choose_match = re.fullmatch(r"voice_action:choose:(cancel|reschedule):(.+)", state)
    if choose_match:
        choose_action, raw_ids = choose_match.groups()
        ids = [x for x in raw_ids.split(",") if x]
        choices = db.scalars(select(Appointment).where(
            Appointment.id.in_(ids),
            Appointment.tenant_id == tenant.id,
            Appointment.customer_id == customer.id,
            Appointment.status.in_(ACTIVE_STATUSES),
        ).order_by(Appointment.starts_at.asc())).all()
        value = " ".join((message or "").casefold().split())
        chosen = None
        number_match = re.search(r"\b(first|1|second|2|third|3|fourth|4)\b", value)
        if number_match:
            ordinal = {"first": 1, "1": 1, "second": 2, "2": 2, "third": 3, "3": 3, "fourth": 4, "4": 4}[number_match.group(1)]
            if ordinal <= len(choices):
                chosen = choices[ordinal - 1]
        if not chosen:
            for candidate in choices:
                local_when = _when(candidate, tenant).casefold()
                if local_when in value or all(token in value for token in local_when.replace(",", "").split() if token not in {"at", "on"}):
                    chosen = candidate
                    break
        if not chosen:
            return {"reply": "Please identify the appointment by its date and time, or say first, second, or third.",
                    "appointment_action": {"status": "needs_clarification", "action": choose_action,
                                           "appointment_ids": ids}}
        if choose_action == "cancel":
            if conversation:
                conversation.state = f"voice_action:cancel_confirm:{chosen.id}"
            return {"reply": f"I found your appointment for {_when(chosen, tenant)}. Do you want me to cancel this appointment?",
                    "appointment_action": {"status": "awaiting_confirmation", "action": "cancel",
                                           "appointment_id": chosen.id}}
        if conversation:
            conversation.state = f"voice_action:reschedule_wait:{chosen.id}"
        return {"reply": f"I found your appointment for {_when(chosen, tenant)}. What new date and time would you prefer? Please include AM or PM.",
                "appointment_action": {"status": "awaiting_new_time", "action": "reschedule",
                                       "appointment_id": chosen.id}}

    # New cancellation/reschedule request: locate the customer's active appointments.
    intent = _action_intent(message)
    if not intent:
        return None
    rows = _upcoming(db, tenant.id, customer.id)
    if not rows:
        return {"reply": "I couldn't find an active upcoming appointment for this mobile number. I haven't changed anything.",
                "appointment_action": {"status": "not_found", "action": intent}}
    if len(rows) > 1:
        options = "; ".join(f"{i + 1}: {_when(a)}" for i, a in enumerate(rows[:4]))
        # Do not guess when there are multiple appointments. The next response must identify one.
        if conversation:
            conversation.state = f"voice_action:choose:{intent}:" + ",".join(a.id for a in rows[:4])
        return {"reply": f"I found more than one upcoming appointment: {options}. Which one do you mean?",
                "appointment_action": {"status": "needs_clarification", "action": intent,
                                       "appointment_ids": [a.id for a in rows[:4]]}}
    appointment = rows[0]
    if intent == "cancel":
        if conversation:
            conversation.state = f"voice_action:cancel_confirm:{appointment.id}"
        return {"reply": f"I found your appointment for {_when(appointment, tenant)}. Do you want me to cancel this appointment?",
                "appointment_action": {"status": "awaiting_confirmation", "action": "cancel",
                                       "appointment_id": appointment.id}}
    if conversation:
        conversation.state = f"voice_action:reschedule_wait:{appointment.id}"
    return {"reply": f"I found your appointment for {_when(appointment, tenant)}. What new date and time would you prefer? Please include AM or PM.",
            "appointment_action": {"status": "awaiting_new_time", "action": "reschedule",
                                   "appointment_id": appointment.id}
}
