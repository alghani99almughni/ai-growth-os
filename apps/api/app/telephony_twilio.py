"""Twilio Media Streams adapter for AI Growth OS.

This is an additive phone-channel adapter. It reuses tenant data, approved
knowledge, CRM models and platform notification services; it does not replace
the existing browser/WebRTC voice runtime.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

import httpx
import websockets
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import select

from .config import settings
from .db import SessionLocal
from .models import Customer, Lead, Tenant
from .models_ai import ReceptionAlert
from .models_ai_voice import DidNumber, SipTrunk, VoiceAgentConfig
from .models_growth import CallRecord
from .services import normalize_phone, upsert_customer

log = logging.getLogger("api.telephony.twilio")
router = APIRouter(tags=["AI Voice Telephony"])

TWILIO_MEDIA_PATH = "/ws/telephony/twilio/media-stream"
E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "save_customer_identity",
            "description": "Save the caller's confirmed name and mobile number in the tenant CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caller_name": {"type": "string"},
                    "phone_number": {"type": "string"},
                },
                "required": ["caller_name", "phone_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_callback_message",
            "description": "Save a caller's callback request or enquiry in the tenant CRM.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caller_name": {"type": "string"},
                    "phone_number": {"type": "string"},
                    "inquiry_summary": {"type": "string"},
                    "urgency": {"type": "string", "enum": ["normal", "urgent"]},
                },
                "required": ["caller_name", "phone_number", "inquiry_summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp_info",
            "description": "Send the business address or PWA link to the caller on WhatsApp after they explicitly request it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone_number": {"type": "string"},
                    "info_type": {"type": "string", "enum": ["location_pin", "brochure", "booking_link"]},
                },
                "required": ["phone_number", "info_type"],
            },
        },
    },
]


def _stream_token(call_sid: str, called: str, caller: str) -> str:
    message = "|".join((call_sid, called, caller))
    return hmac.new(settings.jwt_secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def _valid_stream_token(call_sid: str, called: str, caller: str, token: str) -> bool:
    if not all((call_sid, called, caller, token)):
        return False
    return hmac.compare_digest(_stream_token(call_sid, called, caller), token)


def _twilio_request_valid(url: str, form: dict[str, str], signature: str | None) -> bool:
    if not settings.telephony_api_key or not signature:
        return False
    try:
        from twilio.request_validator import RequestValidator
        return RequestValidator(settings.telephony_api_key).validate(url, form, signature)
    except Exception:
        log.exception("Twilio signature validation failed")
        return False


def _xml_response(root: ET.Element) -> Response:
    body = ET.tostring(root, encoding="unicode")
    return Response(content='<?xml version="1.0" encoding="UTF-8"?>' + body,
                    media_type="application/xml")


@router.post("/api/v1/telephony/twilio/incoming-call")
async def twilio_incoming_call(request: Request):
    """Twilio voice webhook. The called DID is resolved again at stream start."""
    if not settings.ai_voice_enabled:
        raise HTTPException(503, "Phone AI voice is disabled")
    form_data = await request.form()
    form = {str(k): str(v) for k, v in form_data.items()}
    signature = request.headers.get("X-Twilio-Signature")
    if not _twilio_request_valid(str(request.url), form, signature):
        raise HTTPException(403, "Invalid Twilio webhook signature")

    called = normalize_phone(form.get("To", ""))
    caller = normalize_phone(form.get("From", ""))
    call_sid = form.get("CallSid", "")
    if not E164.fullmatch(called) or not call_sid:
        raise HTTPException(422, "Twilio call is missing a valid called number or CallSid")

    # The URL must be HTTPS/WSS in production. Use the public API URL rather
    # than trusting an arbitrary Host header supplied by the webhook request.
    from urllib.parse import urlparse
    public = urlparse(settings.api_public_url)
    if public.scheme != "https" or not public.netloc:
        raise HTTPException(503, "A public HTTPS API URL is required for phone voice")
    stream_url = "wss://" + public.netloc + TWILIO_MEDIA_PATH

    root = ET.Element("Response")
    connect = ET.SubElement(root, "Connect")
    stream = ET.SubElement(connect, "Stream", {"url": stream_url, "track": "both_tracks"})
    for name, value in (
        ("callSid", call_sid),
        ("calledNumber", called),
        ("callerNumber", caller),
        ("streamToken", _stream_token(call_sid, called, caller)),
    ):
        ET.SubElement(stream, "Parameter", {"name": name, "value": value})
    return _xml_response(root)


def _resolve_did(db, called_number: str):
    did = db.scalar(select(DidNumber).where(
        DidNumber.e164_number == called_number,
        DidNumber.inbound_enabled.is_(True),
        DidNumber.status == "assigned",
    ))
    if not did or not did.tenant_id:
        return None, None, None
    trunk = db.get(SipTrunk, did.trunk_id)
    tenant = db.get(Tenant, did.tenant_id)
    if not trunk or not tenant or tenant.status != "active":
        return None, None, None
    # This adapter is specifically for Twilio Media Streams. A DID attached
    # to another provider must use that provider's adapter, not this endpoint.
    if (trunk.provider or "").strip().lower() not in {"twilio", "twilio_media_streams"}:
        return None, None, None
    agent = None
    if did.agent_id:
        agent = db.scalar(select(VoiceAgentConfig).where(
            VoiceAgentConfig.id == did.agent_id,
            VoiceAgentConfig.tenant_id == tenant.id,
            VoiceAgentConfig.status == "published",
        ))
    return tenant, did, agent


def _build_system_prompt(db, tenant: Tenant, agent: VoiceAgentConfig | None, customer: Customer) -> str:
    from .brain import knowledge_context
    from .tenant_policy import tenant_policy, policy_context
    from .agent_training import AGENT_TRAINING_CONTEXT

    context = knowledge_context(db, tenant.id)
    policy = tenant_policy(db, tenant.id)
    agent_rules = agent.operating_instructions if agent else ""
    greeting = agent.greeting if agent and agent.greeting else ""
    return f"""You are the AI phone receptionist for {tenant.name}.
Be warm, brisk and helpful. Speak in short natural sentences. Never use markdown or bullet points.
You are speaking on a live telephone call. Ask one question at a time.
Do not invent prices, opening hours, staff names, availability, policies, bookings or payment status.
Use only verified facts in the approved business context. If a fact is missing, offer a callback or human assistance.
The caller's phone number is {customer.phone}. The saved caller name is {customer.name or "not yet known"}.
If the name is unknown, politely ask for it. Do not ask for the mobile number again unless caller ID is unavailable or the caller corrects it.
Once the caller gives their name, confirm the caller ID number and use save_customer_identity to save both.
Before creating a callback request, read back the name, number and enquiry and confirm.
Only call log_callback_message after the caller agrees to a callback/message.
Only call send_whatsapp_info after the caller explicitly asks for the information on WhatsApp.
If the caller requests a person, a callback or cannot be helped safely, offer to record a message.
Use the caller's language when possible. The existing tenant knowledge and voice runtime remain authoritative.
{("AGENT GREETING: " + greeting) if greeting else ""}
{("TENANT AGENT INSTRUCTIONS: " + agent_rules) if agent_rules else ""}
UNIVERSAL AGENT TRAINING:
{AGENT_TRAINING_CONTEXT}
TENANT POLICY:
{policy_context(policy)}
APPROVED TENANT KNOWLEDGE AND LIVE BUSINESS DATA:
{context}
Business timezone: {tenant.timezone}
Business website: {tenant.website or "not configured"}
Business email: {tenant.email or "not configured"}
"""


async def _deepgram_tts(text: str, language: str = "en") -> bytes:
    key = settings.tts_api_key or settings.stt_api_key
    if not key:
        raise RuntimeError("Deepgram TTS key is not configured")
    model = "aura-asteria-en"
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            "https://api.deepgram.com/v1/speak",
            params={"model": model, "encoding": "mulaw", "sample_rate": "8000", "container": "none"},
            headers={"Authorization": "Token " + key, "Content-Type": "application/json"},
            json={"text": text},
        )
        response.raise_for_status()
        return response.content


async def _twilio_speak(ws: WebSocket, stream_sid: str, text: str):
    if not text or not stream_sid:
        return
    audio = await _deepgram_tts(text)
    # Twilio expects raw G.711 mu-law at 8 kHz. Send 20 ms frames and pace
    # them to avoid overflowing the provider's outbound media buffer.
    for offset in range(0, len(audio), 160):
        if ws.client_state.name != "CONNECTED":
            return
        payload = base64.b64encode(audio[offset:offset + 160]).decode("ascii")
        await ws.send_json({"event": "media", "streamSid": stream_sid, "media": {"payload": payload}})
        await asyncio.sleep(0.02)


async def _openai_turn(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    if not settings.openai_api_key:
        raise RuntimeError("OpenAI API key is not configured")
    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": "Bearer " + settings.openai_api_key},
            json={"model": settings.openai_model, "messages": messages, "tools": TOOL_SCHEMAS,
                  "tool_choice": "auto", "temperature": 0.3},
        )
        response.raise_for_status()
        message = response.json()["choices"][0]["message"]
    return (message.get("content") or "").strip(), message.get("tool_calls") or []


async def _execute_voice_tool(name: str, args: dict[str, Any], tenant_id: str,
                              call_id: str, customer_id: str) -> dict[str, Any]:
    db = SessionLocal()
    try:
        tenant = db.get(Tenant, tenant_id)
        call = db.get(CallRecord, call_id)
        customer = db.get(Customer, customer_id)
        if not tenant or not call or call.tenant_id != tenant_id:
            return {"ok": False, "error": "Call context is no longer available"}

        if name == "save_customer_identity":
            caller_name = str(args.get("caller_name") or "").strip()
            phone = normalize_phone(str(args.get("phone_number") or (customer.phone if customer else "")))
            if not caller_name or not E164.fullmatch(phone):
                return {"ok": False, "error": "A caller name and valid international mobile number are required"}
            saved = upsert_customer(db, tenant_id, phone, caller_name, False, source="twilio_voice")
            call.customer_id = saved.id
            db.commit()
            return {"ok": True, "saved_to_crm": True, "customer_id": saved.id}

        if not customer:
            return {"ok": False, "error": "Verified caller identity is required"}

        if name == "log_callback_message":
            caller_name = str(args.get("caller_name") or customer.name or "").strip()
            phone = normalize_phone(str(args.get("phone_number") or customer.phone or ""))
            summary = str(args.get("inquiry_summary") or "").strip()
            urgency = "urgent" if str(args.get("urgency") or "").lower() == "urgent" else "normal"
            if not caller_name or not phone or not summary:
                return {"ok": False, "error": "Caller name, phone number and enquiry are required"}
            customer.name = caller_name
            customer.phone = phone
            db.add(Lead(id=str(uuid.uuid4()), tenant_id=tenant_id, customer_id=customer.id,
                        source="twilio_voice", intent="callback_request",
                        notes=f"{summary}\nUrgency: {urgency}"))
            db.add(ReceptionAlert(
                tenant_id=tenant_id, customer_id=customer.id, call_id=call.id,
                category="callback", priority=urgency, title="Phone callback requested",
                message=f"{caller_name} ({phone}): {summary}",
            ))
            call.human_callback_requested = True
            db.commit()
            # Notify the business contact through existing platform notification
            # channels. Provider failures are recorded, not reported as success.
            results = {}
            if tenant.email:
                from .notifications import send_email
                results["email"] = await send_email(
                    tenant.email, f"Callback requested — {tenant.name}",
                    f"Caller: {caller_name}\nPhone: {phone}\nEnquiry: {summary}\nUrgency: {urgency}\nCall ID: {call.id}",
                )
            if tenant.whatsapp_number or tenant.phone:
                from .notifications import send_platform_whatsapp
                results["whatsapp"] = await send_platform_whatsapp(
                    tenant.whatsapp_number or tenant.phone,
                    f"Callback requested — {tenant.name}\n{caller_name} ({phone})\n{summary}\nUrgency: {urgency}",
                )
            return {"ok": True, "saved_to_crm": True, "notifications": results}

        if name == "send_whatsapp_info":
            requested_phone = normalize_phone(str(args.get("phone_number") or customer.phone))
            if requested_phone != normalize_phone(customer.phone):
                return {"ok": False, "error": "WhatsApp recipient must match the verified caller number"}
            info_type = str(args.get("info_type") or "")
            if info_type == "location_pin":
                if not tenant.address:
                    return {"ok": False, "error": "Business address is not configured"}
                message = f"{tenant.name} address: {tenant.address}"
            elif info_type in {"brochure", "booking_link"}:
                from .config import settings as app_settings
                message = f"{tenant.name}: {app_settings.public_app_url.rstrip('/')}/pwa/{tenant.slug}"
            else:
                return {"ok": False, "error": "Unsupported WhatsApp information type"}
            from .notifications import send_platform_whatsapp
            result = await send_platform_whatsapp(customer.phone, message)
            if result.get("sent"):
                customer.whatsapp_opt_in = True
                db.commit()
            return {"ok": bool(result.get("sent")), "delivery": result}

        return {"ok": False, "error": "Unknown voice action"}
    except Exception:
        db.rollback()
        log.exception("Twilio voice tool failed: %s", name)
        return {"ok": False, "error": "The requested action could not be completed"}
    finally:
        db.close()


async def _finish_call(call_id: str, tenant_id: str, started_at: datetime,
                       transcript: str, customer_id: str | None):
    db = SessionLocal()
    try:
        call = db.get(CallRecord, call_id)
        tenant = db.get(Tenant, tenant_id)
        customer = db.get(Customer, customer_id) if customer_id else None
        if not call or not tenant or call.tenant_id != tenant_id:
            return
        ended = datetime.utcnow()
        call.transcript = transcript[:100000]
        call.ended_at = ended
        call.duration_seconds = max(0, int((ended - started_at).total_seconds()))
        if call.status not in {"handoff_requested", "handoff_unavailable"}:
            call.status = "completed"
        call.resolution = call.resolution or ("callback" if call.human_callback_requested else "ai")
        call.summary = (transcript.strip().splitlines()[-1][:1000] if transcript.strip() else "No transcript captured")
        db.commit()
        # Send a call summary to the business owner using configured platform channels.
        body = (f"Phone call completed — {tenant.name}\nCall ID: {call.id}\n"
                f"Caller: {(customer.name + ' / ' + customer.phone) if customer else 'unknown'}\nDuration: {call.duration_seconds}s\n"
                f"Resolution: {call.resolution}\n\nTranscript:\n{transcript[-5000:]}")
        if tenant.email:
            try:
                from .notifications import send_email
                await send_email(tenant.email, f"Phone call summary — {tenant.name}", body)
            except Exception:
                log.exception("Could not email Twilio call summary")
        if tenant.whatsapp_number or tenant.phone:
            try:
                from .notifications import send_platform_whatsapp
                await send_platform_whatsapp(tenant.whatsapp_number or tenant.phone, body[:3500])
            except Exception:
                log.exception("Could not WhatsApp Twilio call summary")
    finally:
        db.close()


@router.websocket(TWILIO_MEDIA_PATH)
async def twilio_media_stream(ws: WebSocket):
    await ws.accept()
    db = SessionLocal()
    dg = None
    call = None
    tenant = None
    customer = None
    stream_sid = ""
    transcript_lines: list[str] = []
    messages: list[dict[str, Any]] = []
    started_at = datetime.utcnow()
    stop_event = asyncio.Event()
    try:
        # The first Twilio frame is the connected/start lifecycle envelope.
        first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=15))
        if first.get("event") != "connected":
            await ws.close(code=4400)
            return
        start_message = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=15))
        if start_message.get("event") != "start":
            await ws.close(code=4400)
            return
        start = start_message.get("start") or {}
        params = start.get("customParameters") or {}
        call_sid = str(params.get("callSid") or start.get("callSid") or "")
        called = normalize_phone(str(params.get("calledNumber") or ""))
        caller = normalize_phone(str(params.get("callerNumber") or ""))
        token = str(params.get("streamToken") or "")
        stream_sid = str(start.get("streamSid") or "")
        if not _valid_stream_token(call_sid, called, caller, token):
            await ws.close(code=4403)
            return

        tenant, did, agent = _resolve_did(db, called)
        if not tenant or not did:
            await ws.send_json({"event": "error", "message": "This phone number is not assigned to an active AI Voice tenant."})
            await ws.close(code=4404)
            return
        if not E164.fullmatch(caller):
            caller = ""
        if caller:
            customer = db.scalar(select(Customer).where(
                Customer.tenant_id == tenant.id, Customer.phone == caller
            ))
            if not customer:
                customer = upsert_customer(db, tenant.id, caller, "Phone caller", False, source="twilio_voice")
        active_customer_id = customer.id if customer else ""
        call = CallRecord(
            id=str(uuid.uuid4()), tenant_id=tenant.id,
            customer_id=customer.id if customer else None,
            source="twilio", status="connected", started_at=started_at,
            answered_at=started_at,
        )
        db.add(call)
        db.commit()
        db.refresh(call)

        system_prompt = _build_system_prompt(db, tenant, agent, customer) if customer else (
            f"You are the phone receptionist for {tenant.name}. Ask the caller for their mobile number and name. "
            "Never invent business facts. Offer a callback when you cannot resolve a request."
        )
        messages = [{"role": "system", "content": system_prompt}]
        stt_key = settings.stt_api_key or settings.tts_api_key
        if not stt_key:
            raise RuntimeError("Deepgram STT key is not configured")
        dg_url = "wss://api.deepgram.com/v1/listen?model=nova-2&language=en-IN&encoding=mulaw&sample_rate=8000&smart_format=true&interim_results=true&endpointing=400&utterance_end_ms=1000"
        dg = await websockets.connect(
            dg_url, additional_headers={"Authorization": "Token " + stt_key},
            ping_interval=20, ping_timeout=20, max_size=2 * 1024 * 1024,
        )
        greeting = (agent.greeting if agent and agent.greeting else
                    f"Thank you for calling {tenant.name}. May I know your name, please?")
        await _twilio_speak(ws, stream_sid, greeting)
        messages.append({"role": "assistant", "content": greeting})

        async def on_transcript(text: str):
            nonlocal active_customer_id
            clean = " ".join(text.split())
            if not clean:
                return
            transcript_lines.append("CUSTOMER: " + clean)
            messages.append({"role": "user", "content": clean})
            try:
                reply, tool_calls = await _openai_turn(messages)
                if tool_calls:
                    messages.append({"role": "assistant", "content": reply or None, "tool_calls": tool_calls})
                    for tool_call in tool_calls:
                        fn = tool_call.get("function") or {}
                        try:
                            args = json.loads(fn.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            args = {}
                        result = await _execute_voice_tool(
                            fn.get("name", ""), args, tenant.id, call.id,
                            active_customer_id,
                        )
                        if result.get("customer_id"):
                            active_customer_id = str(result["customer_id"])
                        messages.append({
                            "role": "tool", "tool_call_id": tool_call.get("id"),
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                    reply, _ = await _openai_turn(messages)
                if not reply:
                    reply = "I'm sorry, could you please repeat that?"
                transcript_lines.append("AI: " + reply)
                messages.append({"role": "assistant", "content": reply})
                await _twilio_speak(ws, stream_sid, reply)
                call.transcript = "\n".join(transcript_lines)[-100000:]
                call.ai_turns = (call.ai_turns or 0) + 1
                db.commit()
            except Exception:
                log.exception("Twilio voice turn failed call_id=%s", call.id)
                fallback = "I'm sorry, I'm having trouble at the moment. Would you like me to arrange a callback?"
                transcript_lines.append("AI: " + fallback)
                try:
                    await _twilio_speak(ws, stream_sid, fallback)
                except Exception:
                    pass

        async def deepgram_reader():
            async for raw in dg:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", "ignore")
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                if event.get("type") == "Results":
                    alt = ((event.get("channel") or {}).get("alternatives") or [{}])[0]
                    text_value = str(alt.get("transcript") or "").strip()
                    if event.get("is_final") and text_value:
                        transcript_lines.append("CUSTOMER: " + text_value)
                        if event.get("speech_final"):
                            # Join the contiguous final fragments for one caller turn.
                            combined = []
                            while transcript_lines and transcript_lines[-1].startswith("CUSTOMER: "):
                                combined.insert(0, transcript_lines.pop()[10:])
                            if combined:
                                await on_transcript(" ".join(combined))
                elif event.get("type") == "UtteranceEnd":
                    # Deepgram sends this when it detects the end of an utterance.
                    continue

        async def twilio_reader():
            while not stop_event.is_set():
                raw = await ws.receive_text()
                event = json.loads(raw)
                kind = event.get("event")
                if kind == "media" and dg:
                    payload = (event.get("media") or {}).get("payload")
                    if payload:
                        await dg.send(base64.b64decode(payload))
                elif kind == "stop":
                    stop_event.set()
                    return
                elif kind == "mark":
                    continue

        dg_task = asyncio.create_task(deepgram_reader())
        twilio_task = asyncio.create_task(twilio_reader())
        done, pending = await asyncio.wait(
            {dg_task, twilio_task}, return_when=asyncio.FIRST_COMPLETED
        )
        stop_event.set()
        for task in pending:
            task.cancel()
        for task in done:
            try:
                task.result()
            except (WebSocketDisconnect, websockets.ConnectionClosed):
                pass
            except Exception:
                log.exception("Twilio media task failed call_id=%s", call.id if call else None)
    except (WebSocketDisconnect, websockets.ConnectionClosed):
        pass
    except Exception:
        log.exception("Twilio media stream failed")
        try:
            await ws.close(code=1011)
        except Exception:
            pass
    finally:
        if dg is not None:
            try:
                await dg.send(json.dumps({"type": "CloseStream"}))
                await dg.close()
            except Exception:
                pass
        if call is not None and tenant is not None:
            await _finish_call(
                call.id, tenant.id, started_at,
                "\n".join(transcript_lines), customer.id if customer else None,
            )
        db.close()
