"""Offline call ingestion endpoint.

The widget buffers audio + identity when the network is down. When the
internet comes back, it POSTs to /api/v1/voice/offline-call.

This module:
    1. Resolves the tenant
    2. Saves the audio blob
    3. Runs STT on the audio (Vosk if available)
    4. Runs the router orchestrator on the transcript
    5. Sends the reply via WhatsApp / SMS (multi-channel)
    6. Creates a Lead for staff visibility
    7. Records the outcome in offline_calls and call_recordings

Never raises. Always returns a JSON response.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["voice-offline"])


# ---------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------

class OfflineCallPayload(BaseModel):
    tenant_slug: str
    customer_name: str = "Guest"
    customer_phone: str = ""
    customer_email: Optional[str] = None
    audio_base64: Optional[str] = None
    partial_transcript: Optional[str] = None
    language: Optional[str] = None
    call_started_at: Optional[str] = None
    duration_seconds: Optional[int] = 0
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("/offline-call")
async def offline_call(payload: OfflineCallPayload, request: Request):
    from .db import SessionLocal

    db = SessionLocal()
    try:
        # ---- 1. Resolve tenant --------------------------------------------
        from .models import Tenant
        tenant = db.scalar(select(Tenant).filter_by(slug=payload.tenant_slug))
        if tenant is None:
            return JSONResponse(
                status_code=404,
                content={"error": "tenant_not_found", "slug": payload.tenant_slug},
            )

        # ---- 2. Create the OfflineCall row --------------------------------
        from .models_offline import OfflineCall
        offline = OfflineCall(
            tenant_id=tenant.id,
            customer_name=payload.customer_name or "Guest",
            customer_phone=payload.customer_phone or "",
            customer_email=payload.customer_email,
            channel="widget_offline",
            language=payload.language or "en",
            call_started_at=_parse_dt(payload.call_started_at),
            status="received",
        )
        db.add(offline)
        db.commit()
        db.refresh(offline)
        offline_id = offline.id

        # ---- 3. Save the audio blob ---------------------------------------
        audio_bytes = None
        audio_url = None
        if payload.audio_base64:
            try:
                audio_bytes = base64.b64decode(payload.audio_base64)
                from .call_storage import save_audio
                audio_url = save_audio(
                    audio_bytes,
                    call_id=f"offline_{offline_id}",
                    turn_id="t1",
                    side="customer",
                )
                offline.audio_url = audio_url
                offline.audio_size_bytes = len(audio_bytes)
                offline.audio_duration_seconds = int(payload.duration_seconds or 0)
                db.commit()
            except Exception as exc:
                logger.debug("offline audio save failed: %s", exc)

        # ---- 4. Transcribe (Vosk) or use partial transcript ---------------
        transcript = ""
        if audio_bytes:
            try:
                from .offline_stt import transcribe
                transcript = transcribe(
                    audio_bytes,
                    language=payload.language or "en",
                    stub_text=payload.partial_transcript or "",
                )
            except Exception as exc:
                logger.debug("transcribe failed: %s", exc)
                transcript = payload.partial_transcript or ""
        elif payload.partial_transcript:
            transcript = payload.partial_transcript

        offline.transcript = transcript
        offline.status = "transcribing"
        db.commit()

        # ---- 5. Route through the orchestrator ----------------------------
        reply = ""
        intent = "unknown"
        language = payload.language or "en"
        try:
            from .router_orchestrator import route_message
            from .crm import find_contact
            customer = None
            if payload.customer_phone:
                customer = find_contact(phone=payload.customer_phone)
            result = await route_message(
                db,
                tenant,
                customer,
                transcript or "[offline call - audio could not be transcribed]",
                conversation_id=None,
                channel="offline_recovered",
            )
            reply = result.reply
            intent = result.intent
            language = result.language or language
        except Exception as exc:
            logger.exception("offline orchestrator failed: %s", exc)
            reply = "I'll have the team reach out to you shortly."
            intent = "offline_recovery"

        offline.reply = reply
        offline.intent = intent
        offline.language_detected = language

        # ---- 6. Notify via WhatsApp / SMS ---------------------------------
        whatsapp_ok = False
        sms_ok = False
        email_ok = False
        if payload.customer_phone or payload.customer_email:
            try:
                from .messaging_multi import notify_customer
                result = notify_customer(
                    db, tenant,
                    phone=payload.customer_phone or None,
                    email=payload.customer_email or None,
                    subject=f"Message from {tenant.name}",
                    body_text=reply,
                    prefer="whatsapp",
                )
                whatsapp_ok = bool((result.get("whatsapp") or {}).get("ok"))
                sms_ok = bool((result.get("sms") or {}).get("ok"))
                email_ok = bool((result.get("email") or {}).get("ok"))
            except Exception as exc:
                logger.debug("offline notify failed: %s", exc)

        offline.whatsapp_ok = whatsapp_ok
        offline.sms_ok = sms_ok
        offline.email_ok = email_ok

        # ---- 7. Create the staff Lead -------------------------------------
        lead_id = None
        try:
            from .models import Lead
            lead = Lead(
                tenant_id=tenant.id,
                customer_id=None,
                customer_name=payload.customer_name or "Guest",
                mobile=payload.customer_phone or "",
                intent="offline_recovered",
                source="widget_offline",
                status="new",
                notes=(transcript or "")[:500],
            )
            db.add(lead)
            db.commit()
            lead_id = lead.id
        except Exception as exc:
            logger.debug("offline lead create failed: %s", exc)

        offline.lead_id = lead_id
        offline.status = "processed"
        offline.processed_at = datetime.utcnow()
        db.commit()

        # ---- 8. Also capture into CallRecording for the dashboard ---------
        try:
            from .call_recorder import record_offline_call
            record_offline_call(
                db, tenant.id,
                customer_name=payload.customer_name or "Guest",
                customer_phone=payload.customer_phone or "",
                language=language,
                turn_pairs=[{
                    "customer_text": transcript,
                    "ai_text": reply,
                    "intent": intent,
                    "customer_audio": audio_bytes,
                }],
                outcome="offline_recovered",
            )
        except Exception as exc:
            logger.debug("offline call capture failed: %s", exc)

        return {
            "ok": True,
            "offline_call_id": offline_id,
            "transcript": transcript,
            "reply": reply,
            "intent": intent,
            "language": language,
            "channels": {
                "whatsapp": whatsapp_ok,
                "sms": sms_ok,
                "email": email_ok,
            },
            "lead_id": lead_id,
        }

    except Exception as exc:
        logger.exception("offline_call crashed: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": str(exc)[:200]},
        )
    finally:
        try:
            db.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_dt(value: Optional[str]):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None