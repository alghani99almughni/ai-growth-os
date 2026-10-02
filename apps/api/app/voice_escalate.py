"""
Path A — Gemini Live escalation.

The customer's widget first runs the deterministic brain (Path B) via
/voice/turn. When the brain cannot answer, the widget POSTs to
/voice/escalate and then opens the WebSocket at /ws/escalate/{call_id}
to stream audio bidirectionally with Gemini Live.

If GOOGLE_API_KEY is missing, the WebSocket sends a graceful
"no_agent_available" status and the widget falls back to human handoff.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import Tenant, Customer
from .models import Service
from .models_growth import CallRecord, BusinessHour
from .brain import knowledge_context
from .agent_training import AGENT_TRAINING_CONTEXT
from .tenant_policy import tenant_policy, policy_context, capability_enabled
from .ai_router import detect_language
from datetime import datetime, time
from zoneinfo import ZoneInfo

logger = logging.getLogger("api.voice_escalate")

router = APIRouter()


# --------------------------------------------------------------------------
# Fallback prompt spoken to the customer when we hand over to Gemini Live
# --------------------------------------------------------------------------
HOLD_MESSAGES = {
    "en": "Please hold on while we connect you to the right executive.",
    "hi": "कृपया प्रतीक्षा करें, हम आपको हमारी टीम से जोड़ रहे हैं।",
    "te": "దయచేసి వేచి ఉండండి, మేము మిమ్మల్ని మా టీమ్‌కు కనెక్ట్ చేస్తున్నాము.",
    "ta": "தயவுசெய்து காத்திருங்கள், நாங்கள் உங்களை எங்கள் குழுவுடன் இணைக்கிறோம்.",
    "kn": "ದಯವಿಟ್ಟು ನಿರೀಕ್ಷಿಸಿ, ನಾವು ನಿಮ್ಮನ್ನು ನಮ್ಮ ತಂಡಕ್ಕೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇವೆ.",
    "ml": "ദയവായി കാത്തിരിക്കുക, ഞങ്ങൾ നിങ്ങളെ ഞങ്ങളുടെ ടീമുമായി ബന്ധിപ്പിക്കുന്നു.",
    "mr": "कृपया थांबा, आम्ही तुम्हाला आमच्या टीमशी जोडत आहोत.",
    "bn": "অনুগ্রহ করে অপেক্ষা করুন, আমরা আপনাকে আমাদের দলের সাথে সংযুক্ত করছি।",
    "gu": "કૃપા કરીને રાહ જુઓ, અમે તમને અમારી ટીમ સાથે જોડી રહ્યા છીએ.",
    "pa": "ਕਿਰਪਾ ਕਰਕੇ ਉਡੀਕ ਕਰੋ, ਅਸੀਂ ਤੁਹਾਨੂੰ ਸਾਡੀ ਟੀਮ ਨਾਲ ਜੋੜ ਰਹੇ ਹਾਂ।",
    "ur": "براہ کرم انتظار کریں، ہم آپ کو ہماری ٹیم سے جوڑ رہے ہیں۔",
}


@router.get("/api/v1/public/business/{slug}/voice/escalate/hold-line")
def get_hold_line(slug: str, language: str = "en"):
    return {"language": language, "message": HOLD_MESSAGES.get(language, HOLD_MESSAGES["en"])}


@router.websocket("/ws/escalate/{call_id}")
async def voice_escalate(websocket: WebSocket, call_id: str):
    """
    Bridge the browser's microphone to Gemini Live and stream Gemini's
    audio back. The widget sends JSON frames:
        {"type":"audio","data":"<base64 PCM16 16kHz mono>"}
        {"type":"text","text":"..."}
        {"type":"stop"}
    The server sends JSON frames:
        {"type":"status","status":"connected","provider":"gemini"}
        {"type":"transcript","role":"customer","text":"..."}
        {"type":"transcript","role":"ai","text":"..."}
        {"type":"audio","data":"<base64 PCM16 24kHz mono>"}
        {"type":"error","code":"...","message":"..."}
        {"type":"status","status":"ended"}
    """
    await websocket.accept()
    logger.info("escalate ws accepted call_id=%s", call_id)

    db: Session = SessionLocal()
    try:
        call = db.get(CallRecord, call_id)
        if not call:
            await websocket.send_json({"type": "error", "code": "call_not_found", "message": "Call session not found."})
            await websocket.close(code=4404)
            return

        tenant = db.get(Tenant, call.tenant_id)
        if not tenant:
            await websocket.send_json({"type": "error", "code": "tenant_not_found", "message": "Business not found."})
            await websocket.close(code=4404)
            return

        if not settings.gemini_api_key:
            await websocket.send_json({
                "type": "error",
                "code": "no_agent_available",
                "message": "No AI agent is configured. Escalating to a human.",
            })
            await websocket.close(code=1011)
            return

        customer = db.get(Customer, call.customer_id) if call.customer_id else None
        policy = tenant_policy(db, tenant.id)
        context = knowledge_context(db, tenant.id)

        system_prompt = _build_system_prompt(tenant, customer, policy, context)

        # Import here so the module is optional at deploy time.
        try:
            from google import genai
            from google.genai import types as genai_types
        except Exception as exc:
            logger.exception("gemini SDK import failed")
            await websocket.send_json({"type": "error", "code": "sdk_missing", "message": "AI SDK unavailable on the server."})
            await websocket.close(code=1011)
            return

        client = genai.Client(api_key=settings.gemini_api_key)
        model_name = getattr(settings, "gemini_live_model", None) or "gemini-2.0-flash-exp"

        async def run_session():
            try:
                # google-genai Live API is exposed as client.aio.live.connect
                async with client.aio.live.connect(
                    model=model_name,
                    config=genai_types.LiveConnectConfig(
                        response_modalities=["AUDIO"],
                        system_instruction=genai_types.Content(
                            parts=[genai_types.Part(text=system_prompt)]
                        ),
                    ),
                ) as session:
                    await websocket.send_json({
                        "type": "status",
                        "status": "connected",
                        "provider": "gemini",
                        "model": model_name,
                    })

                    # Nudge Gemini to greet.
                    await session.send_client_content(
                        turns=[genai_types.Content(role="user", parts=[genai_types.Part(text="Begin the call now.")])],
                        turn_complete=True,
                    )

                    async def pump_in():
                        try:
                            while True:
                                raw = await websocket.receive_text()
                                msg = json.loads(raw)
                                mtype = msg.get("type")
                                if mtype == "audio":
                                    pcm = base64.b64decode(msg.get("data", ""))
                                    await session.send_realtime_input(
                                        audio=genai_types.Blob(data=pcm, mime_type="audio/pcm;rate=16000")
                                    )
                                elif mtype == "text":
                                    await session.send_client_content(
                                        turns=[genai_types.Content(role="user", parts=[genai_types.Part(text=msg.get("text", ""))])],
                                        turn_complete=True,
                                    )
                                elif mtype == "stop":
                                    break
                        except WebSocketDisconnect:
                            return
                        except Exception:
                            logger.exception("escalate pump_in failed")
                            return

                    async def pump_out():
                        try:
                            async for response in session.receive():
                                sc = getattr(response, "server_content", None)
                                if sc is None:
                                    continue
                                inp = getattr(sc, "input_transcription", None)
                                out = getattr(sc, "output_transcription", None)
                                if inp and getattr(inp, "text", None):
                                    await websocket.send_json({"type": "transcript", "role": "customer", "text": inp.text})
                                if out and getattr(out, "text", None):
                                    await websocket.send_json({"type": "transcript", "role": "ai", "text": out.text})
                                mt = getattr(sc, "model_turn", None)
                                parts = getattr(mt, "parts", None) if mt else None
                                if parts:
                                    for p in parts:
                                        inline = getattr(p, "inline_data", None)
                                        if inline and getattr(inline, "data", None):
                                            await websocket.send_json({
                                                "type": "audio",
                                                "data": base64.b64encode(inline.data).decode("ascii"),
                                                "sample_rate": 24000,
                                            })
                        except Exception:
                            logger.exception("escalate pump_out failed")

                    await asyncio.gather(pump_in(), pump_out())
            except Exception:
                logger.exception("gemini live session crashed call_id=%s", call_id)
                try:
                    await websocket.send_json({"type": "error", "code": "gemini_unavailable", "message": "AI voice service unavailable."})
                except Exception:
                    pass

        try:
            await run_session()
        finally:
            try:
                await websocket.send_json({"type": "status", "status": "ended"})
            except Exception:
                pass
            try:
                await websocket.close()
            except Exception:
                pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _build_system_prompt(tenant: Tenant, customer: Optional[Customer], policy: dict, context: str) -> str:
    name = customer.name if customer and customer.name else "there"
    try:
        today_local = datetime.now(ZoneInfo(tenant.timezone)).date().isoformat()
    except Exception:
        today_local = datetime.utcnow().date().isoformat()
    return f"""You are the AI customer engagement voice agent for {tenant.name}.

UNIVERSAL AGENT TRAINING:
{AGENT_TRAINING_CONTEXT}

TENANT POLICY:
{policy_context(policy)}

APPROVED BUSINESS CONTEXT:
{context}

Today in the business timezone is {today_local}.

The customer has already given their name ({name}) and mobile number.
Do NOT ask for those again.

Behaviour:
- Reply in the customer's language. Default English, but switch to Hindi,
  Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi,
  or Urdu the moment the customer speaks it.
- If the customer mixes English with an Indian language, mirror the mix.
- Be warm, concise, natural. Do not read data lists.
- Never invent prices, availability, policies, bookings or payment success.
- Use the approved business context for hours, services, doctors, booking
  rules, complaints, waiter/water/food/laundry requests, accounts, and any
  industry-specific information.
- If a caller pauses or is garbled, ask them to repeat. Do not hang up.
- If the customer asks for a human, say you'll connect them to the team.
"""