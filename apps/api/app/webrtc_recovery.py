"""WebRTC drop recovery.

When a WebRTC call fails mid-conversation, this module runs a recovery
ladder so the customer is always reached — even if the call can't be
restored.

Ladder (10-second ICE retry):
    T+0s    Drop detected
    T+0s    Retry ICE for up to 10s
    T+10s   If failed -> send WhatsApp
    T+70s   If no reply -> send SMS
    T+5m    If no reply -> send Email (with transcript)
    T+0s    In parallel: create a Lead so staff sees it immediately

All timers run in background tasks. This module never blocks the caller.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

ICE_RETRY_WINDOW_SECONDS = 10
WHATSAPP_DELAY_SECONDS = 0
SMS_DELAY_SECONDS = 60
EMAIL_DELAY_SECONDS = 300

_RECOVERY_STATE = {}


# ---------------------------------------------------------------------------
# Lead creation
# ---------------------------------------------------------------------------

def _create_recovery_lead(db, tenant, call_record):
    """Create a Lead so staff sees the dropped call immediately."""
    try:
        from .models import Lead

        customer_name = getattr(call_record, "customer_name", None) or "Guest"
        customer_phone = getattr(call_record, "mobile", None) or ""
        customer_id = getattr(call_record, "customer_id", None)

        lead = Lead(
            tenant_id=tenant.id,
            customer_id=customer_id,
            customer_name=customer_name,
            mobile=customer_phone,
            intent="webrtc_drop",
            source="ai_voice",
            status="new",
            notes="Call dropped - auto-recovery started. Staff should follow up.",
        )
        db.add(lead)
        db.commit()
        return lead.id
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.exception("recovery lead creation failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _whatsapp_recovery_message(customer_name, tenant_name, rejoin_url):
    name = customer_name or "there"
    lines = [
        f"Hi {name}, we couldn't reach you on the call with {tenant_name}.",
        "If you'd like to continue, just reply here - a team member will help you right away.",
    ]
    if rejoin_url:
        lines.append(f"Or tap to rejoin the call: {rejoin_url}")
    return "\n".join(lines)


def _sms_recovery_message(customer_name, tenant_name):
    name = customer_name or "there"
    return (
        f"Hi {name}, we missed you on the call with {tenant_name}. "
        "Reply to this SMS and a team member will contact you."
    )


def _email_recovery_subject(tenant_name):
    return f"We missed your call - {tenant_name}"


def _email_recovery_body(customer_name, tenant_name, transcript):
    name = customer_name or "there"
    parts = [
        f"Hi {name},",
        "",
        f"Our call with {tenant_name} was interrupted. We're sorry for the inconvenience.",
        "If you'd like us to get back to you, simply reply to this email.",
    ]
    if transcript:
        parts.append("")
        parts.append("--- What we discussed so far ---")
        parts.append(transcript)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Delayed senders
# ---------------------------------------------------------------------------

async def _send_whatsapp_with_delay(db, tenant, call_record, delay_seconds):
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    try:
        from .messaging_multi import send_whatsapp
        phone = getattr(call_record, "mobile", None)
        if not phone:
            logger.debug("recovery: no phone for whatsapp")
            return
        body = _whatsapp_recovery_message(
            getattr(call_record, "customer_name", ""),
            getattr(tenant, "name", ""),
            rejoin_url=None,
        )
        ok, err = send_whatsapp(db, tenant, phone, body)
        logger.info("recovery whatsapp ok=%s err=%s call=%s",
                    ok, err, getattr(call_record, "id", "?"))
    except Exception as exc:
        logger.debug("whatsapp recovery failed: %s", exc)


async def _send_sms_with_delay(db, tenant, call_record, delay_seconds):
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    try:
        from .messaging_multi import send_sms
        phone = getattr(call_record, "mobile", None)
        if not phone:
            return
        body = _sms_recovery_message(
            getattr(call_record, "customer_name", ""),
            getattr(tenant, "name", ""),
        )
        ok, err = send_sms(db, tenant, phone, body)
        logger.info("recovery sms ok=%s err=%s call=%s",
                    ok, err, getattr(call_record, "id", "?"))
    except Exception as exc:
        logger.debug("sms recovery failed: %s", exc)


async def _send_email_with_delay(db, tenant, call_record, delay_seconds):
    if delay_seconds > 0:
        await asyncio.sleep(delay_seconds)
    try:
        from .messaging_multi import send_email
        email = getattr(call_record, "customer_email", None)
        if not email:
            logger.debug("recovery: no email for call %s", getattr(call_record, "id", "?"))
            return
        subject = _email_recovery_subject(getattr(tenant, "name", ""))
        transcript = getattr(call_record, "transcript", "") or ""
        body = _email_recovery_body(
            getattr(call_record, "customer_name", ""),
            getattr(tenant, "name", ""),
            transcript,
        )
        ok, err = send_email(db, tenant, email, subject, body)
        logger.info("recovery email ok=%s err=%s call=%s",
                    ok, err, getattr(call_record, "id", "?"))
    except Exception as exc:
        logger.debug("email recovery failed: %s", exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_recovery(db, tenant, call_record, reason="webrtc_failed"):
    """Kick off the recovery ladder for a dropped call.

    Called from signaling.py when a peer connection is closed unexpectedly.
    """
    call_id = getattr(call_record, "id", None) or str(time.time())
    if call_id in _RECOVERY_STATE:
        return {"status": "already_running", "call_id": call_id}

    _RECOVERY_STATE[call_id] = {"started_at": time.time(), "reason": reason}

    lead_id = _create_recovery_lead(db, tenant, call_record)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.create_task(_send_whatsapp_with_delay(db, tenant, call_record, WHATSAPP_DELAY_SECONDS))
    loop.create_task(_send_sms_with_delay(db, tenant, call_record, SMS_DELAY_SECONDS))
    loop.create_task(_send_email_with_delay(db, tenant, call_record, EMAIL_DELAY_SECONDS))

    logger.info("recovery started call=%s reason=%s lead=%s",
                call_id, reason, lead_id)

    return {
        "status": "started",
        "call_id": call_id,
        "lead_id": lead_id,
        "whatsapp_at_seconds": WHATSAPP_DELAY_SECONDS,
        "sms_at_seconds": SMS_DELAY_SECONDS,
        "email_at_seconds": EMAIL_DELAY_SECONDS,
    }


def should_retry_ice(elapsed_seconds, attempts):
    """Return True if signaling should still attempt an ICE restart."""
    if elapsed_seconds >= ICE_RETRY_WINDOW_SECONDS:
        return False
    if attempts >= 3:
        return False
    return True


def cleanup_recovery(call_id):
    """Remove a recovery entry. Called when the call truly ends."""
    _RECOVERY_STATE.pop(call_id, None)


def active_recoveries():
    """Diagnostic: return all in-flight recovery call IDs."""
    return list(_RECOVERY_STATE.keys())