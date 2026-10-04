"""
Layer 2: Gemini Live escalation (the "specialist AI", uses tokens).

The customer's widget first runs the deterministic brain via /voice/turn. When the
brain cannot answer, the widget opens the WebSocket at /ws/escalate/{call_id} and
streams audio both ways with Gemini Live.

Frames from the widget:
    {"type":"audio","data":"<base64 PCM16 16kHz mono>"}
    {"type":"text","text":"..."}        (first one is the hand-over context)
    {"type":"stop"}
Frames to the widget:
    {"type":"status","status":"connected","provider":"gemini","model":"..."}
    {"type":"transcript","role":"customer"|"ai","text":"..."}
    {"type":"audio","data":"<base64 PCM16 24kHz mono>","sample_rate":24000}
    {"type":"interruption"}
    {"type":"handoff_required","reason":"..."}   specialist wants a human; widget moves to Layer 3
    {"type":"error","code":"...","message":"..."} the session died; widget moves to Layer 3
    {"type":"status","status":"ended"}            normal end only

What changed compared with the previous version (and why):
  * session.receive() only yields ONE model turn and then stops. It is now called in a loop.
    Before, nothing read Gemini's replies after the first turn, the socket buffer filled up,
    pongs were never processed and the connection died with "1011 keepalive ping timeout".
  * input/output transcription is switched on (the old code listened for transcripts that were
    never enabled).
  * the specialist has a request_human_handoff tool, so "connect me to the team" actually moves the
    call to Layer 3 instead of only being said out loud.
  * a crash now sends an error frame before "ended", so the widget falls through to a human
    instead of showing "Call ended".
  * barge-in is forwarded, the hand-over text and the greeting are one turn instead of two,
    the DB session is released as soon as the prompt is built, the transcript is saved on the call
    record, and a hard time limit protects token spend.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import Tenant, Customer
from .models_growth import CallRecord
from .brain import knowledge_context
from .agent_training import AGENT_TRAINING_CONTEXT
from .tenant_policy import tenant_policy, policy_context

logger = logging.getLogger("api.voice_escalate")

router = APIRouter()

MAX_SESSION_SECONDS = 420          # after this the customer is handed to a human instead of burning tokens
FIRST_TEXT_WAIT_SECONDS = 2.5      # how long to wait for the hand-over context before greeting anyway
HANDOFF_FALLBACK_SECONDS = 6.0     # if turn_complete never arrives after the tool call
TRANSCRIPT_SEPARATOR = "\\n"       # call.transcript uses a literal backslash-n between lines (see main.py)

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


DEFAULT_LIVE_MODEL = "gemini-2.5-flash-native-audio-latest"


def _live_model(name: Optional[str]) -> str:
    """Only Live-capable model ids work here. 'gemini-2.5-flash' (the config.py default) and the old
    'gemini-live-2.5-flash-native-audio' are rejected by Google, so map them to a valid one."""
    n = (name or "").strip()
    if n.startswith("models/"):
        n = n[len("models/"):]
    if n == "gemini-live-2.5-flash-native-audio" or not ("live" in n or "audio" in n):
        return DEFAULT_LIVE_MODEL
    return n


class _TranscriptBuffer:
    """Gemini sends transcription in small chunks; join them into whole turns before saving."""

    def __init__(self) -> None:
        self.turns: list[tuple[str, str]] = []
        self._role: Optional[str] = None
        self._text = ""

    def add(self, role: str, text: str) -> None:
        if role != self._role:
            self.flush()
            self._role = role
        self._text += text

    def flush(self) -> None:
        if self._role and self._text.strip():
            self.turns.append((self._role, " ".join(self._text.split())))
        self._role, self._text = None, ""

    def lines(self) -> list[str]:
        self.flush()
        return [("CUSTOMER: " if role == "customer" else "AI: ") + text for role, text in self.turns]


def _save_transcript(call_id: str, lines: list[str]) -> None:
    if not lines:
        return
    db = SessionLocal()
    try:
        call = db.get(CallRecord, call_id)
        if call:
            extra = TRANSCRIPT_SEPARATOR.join(lines)
            call.transcript = ((call.transcript + TRANSCRIPT_SEPARATOR) if call.transcript else "") + extra
            db.commit()
    except Exception:
        db.rollback()
        logger.exception("escalate transcript save failed call_id=%s", call_id)
    finally:
        db.close()


def _live_config(genai_types, system_prompt: str):
    """Build the Live config. Falls back to the minimal config if this SDK version rejects an option."""
    base = dict(
        response_modalities=["AUDIO"],
        system_instruction=genai_types.Content(parts=[genai_types.Part(text=system_prompt)]),
    )
    try:
        extras = dict(
            input_audio_transcription=genai_types.AudioTranscriptionConfig(),
            output_audio_transcription=genai_types.AudioTranscriptionConfig(),
            tools=[genai_types.Tool(function_declarations=[
                genai_types.FunctionDeclaration(
                    name="request_human_handoff",
                    description=(
                        "Call this when the customer asks for a human, manager or supervisor, or when you cannot "
                        "resolve their request. Say one short sentence telling them you are connecting them to the "
                        "team, then call this."
                    ),
                    parameters={
                        "type": "OBJECT",
                        "properties": {"reason": {"type": "STRING", "description": "Why a human is needed."}},
                    },
                ),
            ])],
        )
        return genai_types.LiveConnectConfig(**base, **extras), True
    except Exception:
        logger.exception("full Live config rejected by SDK; using minimal config (no transcripts, no handoff tool)")
        return genai_types.LiveConnectConfig(**base), False


@router.websocket("/ws/escalate/{call_id}")
async def voice_escalate(websocket: WebSocket, call_id: str):
    await websocket.accept()
    logger.info("escalate ws accepted call_id=%s", call_id)

    system_prompt = ""
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
            await websocket.send_json({"type": "error", "code": "no_agent_available",
                                       "message": "No AI agent is configured. Escalating to a human."})
            await websocket.close(code=1011)
            return
        customer = db.get(Customer, call.customer_id) if call.customer_id else None
        policy = tenant_policy(db, tenant.id)
        context = knowledge_context(db, tenant.id)
        system_prompt = _build_system_prompt(tenant, customer, policy, context)
    finally:
        db.close()   # do not hold a pooled connection for the whole call

    try:
        from google import genai
        from google.genai import types as genai_types
    except Exception:
        logger.exception("gemini SDK import failed")
        await websocket.send_json({"type": "error", "code": "sdk_missing", "message": "AI SDK unavailable on the server."})
        await websocket.close(code=1011)
        return

    client = genai.Client(api_key=settings.gemini_api_key)
    model_name = _live_model(getattr(settings, "gemini_live_model", None))
    config, has_tools = _live_config(genai_types, system_prompt)
    buffer = _TranscriptBuffer()
    outcome = {"crashed": False, "handoff": False}

    async def run_session() -> None:
        async with client.aio.live.connect(model=model_name, config=config) as session:
            await websocket.send_json({"type": "status", "status": "connected", "provider": "gemini", "model": model_name})

            stop = asyncio.Event()
            opened = {"done": False}
            handoff = {"pending": False, "sent": False, "reason": ""}

            async def send_handoff(reason: str) -> None:
                if handoff["sent"]:
                    return
                handoff["sent"] = True
                outcome["handoff"] = True
                try:
                    await websocket.send_json({"type": "handoff_required", "reason": reason})
                except Exception:
                    pass
                stop.set()

            async def opening_nudge() -> None:
                # Normally the widget's hand-over text opens the conversation; greet anyway if it never arrives.
                await asyncio.sleep(FIRST_TEXT_WAIT_SECONDS)
                if not opened["done"]:
                    opened["done"] = True
                    await session.send_client_content(
                        turns=[genai_types.Content(role="user", parts=[genai_types.Part(text="Begin the call now.")])],
                        turn_complete=True,
                    )

            async def handoff_fallback() -> None:
                await asyncio.sleep(HANDOFF_FALLBACK_SECONDS)
                if handoff["pending"]:
                    await send_handoff(handoff["reason"])

            async def pump_in() -> None:
                while True:
                    raw = await websocket.receive_text()
                    msg = json.loads(raw)
                    kind = msg.get("type")
                    if kind == "audio":
                        pcm = base64.b64decode(msg.get("data", ""))
                        await session.send_realtime_input(audio=genai_types.Blob(data=pcm, mime_type="audio/pcm;rate=16000"))
                    elif kind == "text":
                        text = str(msg.get("text", "")).strip()
                        if not text:
                            continue
                        if not opened["done"]:
                            opened["done"] = True
                            text += ("\n\nGreet the customer by name, say you are taking over from the assistant, "
                                     "and help with their request.")
                        await session.send_client_content(
                            turns=[genai_types.Content(role="user", parts=[genai_types.Part(text=text)])],
                            turn_complete=True,
                        )
                    elif kind == "stop":
                        stop.set()
                        return

            async def handle_tool_call(tool_call) -> None:
                responses = []
                for fc in getattr(tool_call, "function_calls", None) or []:
                    args = dict(getattr(fc, "args", None) or {})
                    if fc.name == "request_human_handoff":
                        handoff["pending"] = True
                        handoff["reason"] = str(args.get("reason") or "Customer needs a human.")
                        asyncio.create_task(handoff_fallback())
                        result = {"ok": True, "note": "The widget is connecting the customer to the team."}
                    else:
                        result = {"ok": False, "note": "Unknown tool."}
                    responses.append(genai_types.FunctionResponse(id=fc.id, name=fc.name, response=result))
                if responses:
                    await session.send_tool_response(function_responses=responses)

            async def pump_out() -> None:
                # session.receive() ends after every completed model turn, so it must be called in a loop.
                while not stop.is_set():
                    got_any = False
                    async for response in session.receive():
                        got_any = True
                        tool_call = getattr(response, "tool_call", None)
                        if tool_call:
                            await handle_tool_call(tool_call)
                        sc = getattr(response, "server_content", None)
                        if sc is None:
                            continue
                        if getattr(sc, "interrupted", False):
                            await websocket.send_json({"type": "interruption"})
                        inp = getattr(sc, "input_transcription", None)
                        out = getattr(sc, "output_transcription", None)
                        if inp and getattr(inp, "text", None):
                            buffer.add("customer", inp.text)
                            await websocket.send_json({"type": "transcript", "role": "customer", "text": inp.text})
                        if out and getattr(out, "text", None):
                            buffer.add("ai", out.text)
                            await websocket.send_json({"type": "transcript", "role": "ai", "text": out.text})
                        model_turn = getattr(sc, "model_turn", None)
                        for part in (getattr(model_turn, "parts", None) or []):
                            inline = getattr(part, "inline_data", None)
                            if inline and getattr(inline, "data", None):
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": base64.b64encode(inline.data).decode("ascii"),
                                    "sample_rate": 24000,
                                })
                        if getattr(sc, "turn_complete", False):
                            buffer.flush()
                            if handoff["pending"]:
                                await send_handoff(handoff["reason"])
                                return
                    if not got_any:
                        await asyncio.sleep(0.05)   # never spin if the stream ends immediately

            async def time_limit() -> None:
                await asyncio.sleep(MAX_SESSION_SECONDS)
                logger.info("escalate time limit reached call_id=%s", call_id)
                await send_handoff("The specialist call reached its time limit.")

            watched = [asyncio.create_task(c()) for c in (pump_in, pump_out, time_limit)]
            tasks = watched + [asyncio.create_task(opening_nudge())]   # the nudge is fire-and-forget
            stopper = asyncio.create_task(stop.wait())
            try:
                done, _pending = await asyncio.wait(watched + [stopper], return_when=asyncio.FIRST_COMPLETED)
                for t in done:
                    if t is stopper or t.cancelled():
                        continue
                    exc = t.exception()
                    if exc is None:
                        continue
                    if isinstance(exc, WebSocketDisconnect):
                        return                          # customer closed the page
                    raise exc
            finally:
                for t in tasks + [stopper]:
                    t.cancel()
                await asyncio.gather(*tasks, stopper, return_exceptions=True)

    try:
        await run_session()
    except WebSocketDisconnect:
        pass
    except Exception:
        outcome["crashed"] = True
        logger.exception("gemini live session crashed call_id=%s", call_id)
        try:
            await websocket.send_json({"type": "error", "code": "gemini_unavailable", "message": "AI voice service unavailable."})
        except Exception:
            pass
    finally:
        await asyncio.to_thread(_save_transcript, call_id, buffer.lines())
        if not outcome["crashed"] and not outcome["handoff"]:
            try:
                await websocket.send_json({"type": "status", "status": "ended"})
            except Exception:
                pass
        try:
            await websocket.close()
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
- If the customer asks for a human, manager or supervisor, or you cannot resolve the request from the
  approved context, say one short sentence that you are connecting them to the team and then call the
  request_human_handoff tool. Never only say it: the tool is what actually transfers the call.
"""
