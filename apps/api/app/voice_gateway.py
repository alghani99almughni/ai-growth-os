"""Provider-neutral realtime voice gateway.

Owns session state, reconnect/failover policy and provider adapter boundaries.
Business logic never talks directly to a realtime vendor.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol
import asyncio, json, time, logging

_log = logging.getLogger("uvicorn.error")

# Old/invalid Gemini Live model names -> currently valid model IDs.
# This makes the fix work even if the old name is still set in an env var on Render.
GEMINI_MODEL_ALIASES = {
    "gemini-live-2.5-flash-native-audio": "gemini-2.5-flash-native-audio-latest",
}
GEMINI_DEFAULT_MODEL = "gemini-2.5-flash-native-audio-latest"


def normalize_gemini_model(name: str | None) -> str:
    """Return a bare, valid Gemini Live model ID (no 'models/' prefix)."""
    name = (name or "").strip()
    if name.startswith("models/"):
        name = name[len("models/"):]
    if not name:
        return GEMINI_DEFAULT_MODEL
    return GEMINI_MODEL_ALIASES.get(name, name)


@dataclass
class VoiceProvider:
    name: str
    model: str
    api_key: str
    priority: int = 100
    enabled: bool = True

@dataclass
class VoiceSessionState:
    call_id: str
    provider_name: str
    started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    customer_transcript: list[str] = field(default_factory=list)
    assistant_transcript: list[str] = field(default_factory=list)
    turn_index: int = 0
    interrupted: bool = False
    reconnects: int = 0
    failovers: int = 0
    # Operational call state shared by provider adapters and the reception layer.
    status: str = "connecting"
    priority: str = "normal"
    department: str | None = None
    staff_id: str | None = None
    resolution: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def transition(self, status: str) -> None:
        allowed = {"connecting","ringing","connected","listening","speaking","on_hold","handoff","ending","ended","failed"}
        if status not in allowed:
            raise ValueError("Invalid voice session state")
        self.status = status
        self.last_activity = time.time()

class VoiceProviderAdapter(Protocol):
    name: str
    async def connect(self, provider: VoiceProvider, *, system_instruction: str, tools: list[dict[str, Any]], state: VoiceSessionState) -> Any: ...
    async def send_audio(self, session: Any, pcm16_b64: str) -> None: ...
    async def interrupt(self, session: Any) -> None: ...
    async def recv(self, session: Any) -> dict[str, Any]: ...
    async def send_text(self, session: Any, text: str) -> None: ...
    async def send_tool_response(self, session: Any, responses: list[dict[str, Any]]) -> None: ...
    async def close(self, session: Any) -> None: ...

class GeminiLiveAdapter:
    name = "gemini"
    async def connect(self, provider, *, system_instruction, tools, state):
        import websockets
        model = normalize_gemini_model(provider.model)
        url = ("wss://generativelanguage.googleapis.com/ws/"
               "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
               "?key=" + provider.api_key)
        ws = await websockets.connect(url, max_size=8*1024*1024, ping_interval=20, ping_timeout=20)
        setup = {"setup":{"model":"models/"+model,
            "generationConfig":{"responseModalities":["AUDIO"]},
            "systemInstruction":{"parts":[{"text":system_instruction}]},
            "inputAudioTranscription":{},"outputAudioTranscription":{},
            "realtimeInputConfig":{"automaticActivityDetection":{"disabled":False,"startOfSpeechSensitivity":"START_SENSITIVITY_HIGH","endOfSpeechSensitivity":"END_SENSITIVITY_LOW","prefixPaddingMs":240,"silenceDurationMs":420}},
            "sessionResumption":{}}}
        if tools:
            setup["setup"]["tools"] = [{"functionDeclarations":tools}]
        try:
            await ws.send(json.dumps(setup))
            # Wait for Gemini to confirm the setup. If the model name is wrong, Google
            # closes the socket here, so the error surfaces inside connect() and the
            # gateway's failover/error handling can react instead of hanging silently.
            first = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(first, bytes):
                first = first.decode()
            if "setupComplete" not in json.loads(first):
                raise RuntimeError("Gemini setup failed: " + first[:300])
        except Exception:
            try: await ws.close()
            except Exception: pass
            raise
        if state.customer_transcript or state.assistant_transcript:
            history = [{"role":"user","parts":[{"text":"Previous call context (resume):\nCustomer: "+c}]} for c in state.customer_transcript[-8:]]
            if state.assistant_transcript:
                history.append({"role":"model","parts":[{"text":"Previous assistant context: "+state.assistant_transcript[-8:][-1]}]})
            await ws.send(json.dumps({"clientContent":{"turns":history,"turnComplete":False}}))
        return ws
    async def send_audio(self, session, pcm16_b64):
        await session.send(json.dumps({"realtimeInput":{"audio":{"data":pcm16_b64,"mimeType":"audio/pcm;rate=16000"}}}))
    async def interrupt(self, session):
        try: await session.send(json.dumps({"clientContent":{"turns":[],"turnComplete":True}}))
        except Exception: pass
    async def recv(self, session):
        raw=await session.recv()
        if isinstance(raw,bytes): raw=raw.decode()
        msg=json.loads(raw)
        # Diagnostic logging (no audio payloads) so Render logs show what Gemini sends.
        try:
            _sc = msg.get("serverContent") or {}
            _parts = (_sc.get("modelTurn") or {}).get("parts") or []
            _only_audio = bool(_parts) and all(("inlineData" in x) for x in _parts) and len(_sc) == 1
            if not _only_audio:
                _log.info("GEMINI_LIVE_MSG keys=%s serverContent=%s parts=%s",
                          list(msg.keys()), list(_sc.keys()),
                          [list(x.keys()) for x in _parts])
            if "goAway" in msg or "error" in msg:
                _log.warning("GEMINI_LIVE_NOTICE %s", json.dumps(msg)[:500])
        except Exception:
            pass
        if (msg.get("serverContent") or {}).get("interrupted"):
            return {"_gateway":{"event":"interruption"}}
        parts=((msg.get("serverContent") or {}).get("modelTurn") or {}).get("parts") or []
        function_calls=[]
        for part in parts:
            fc=part.get("functionCall")
            if fc:
                function_calls.append({
                    "id": fc.get("id") or fc.get("name"),
                    "name": fc.get("name"),
                    "args": fc.get("args") or {}
                })
        if function_calls:
            normalized=dict(msg)
            normalized["toolCall"]={"functionCalls":function_calls}
            return normalized
        return msg
    async def send_text(self, session, text):
        _log.info("GEMINI_LIVE_SEND_TEXT %s", text[:80])
        await session.send(json.dumps({"clientContent":{"turns":[{"role":"user","parts":[{"text":text}]}],"turnComplete":True}}))
    async def send_tool_response(self, session, responses):
        _log.info("GEMINI_LIVE_TOOL_RESPONSE count=%s", len(responses))
        await session.send(json.dumps({"toolResponse":{"functionResponses":responses}}))
    async def close(self, session):
        try: await session.close()
        except Exception: pass

class OpenAIRealtimeAdapter:
    """OpenAI Realtime GA WebSocket adapter.

    The Realtime Beta wire protocol was retired. This adapter intentionally
    speaks the current GA session/event shapes and never sends the legacy
    OpenAI-Beta header.
    """
    name = "openai"

    @staticmethod
    def _session_update(system_instruction: str, tools: list[dict[str, Any]], model: str) -> dict[str, Any]:
        session: dict[str, Any] = {
            "type": "session.update",
            "session": {
                "type": "realtime",
                "model": model,
                "output_modalities": ["audio"],
                "instructions": system_instruction,
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "turn_detection": {
                            "type": "server_vad",
                            "interrupt_response": True,
                            "create_response": True,
                        },
                        "transcription": {"model": "gpt-4o-transcribe"},
                    },
                    "output": {
                        "format": {"type": "audio/pcm", "rate": 24000},
                        "voice": "marin",
                    },
                },
            },
        }
        if tools:
            session["session"]["tools"] = [
                {
                    "type": "function",
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]
            session["session"]["tool_choice"] = "auto"
        return session

    async def connect(self, provider, *, system_instruction, tools, state):
        import websockets

        model = provider.model
        url = "wss://api.openai.com/v1/realtime?model=" + model
        # GA Realtime: do NOT send OpenAI-Beta: realtime=v1.
        ws = await websockets.connect(
            url,
            additional_headers={"Authorization": "Bearer " + provider.api_key},
            max_size=8 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        )

        try:
            # Wait for the GA session to be created before updating it.
            first = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(first, bytes):
                first = first.decode()
            created = json.loads(first)
            if created.get("type") == "error":
                raise RuntimeError(created.get("error", {}).get("message", "Realtime session error"))
            if created.get("type") != "session.created":
                raise RuntimeError("Unexpected OpenAI realtime event: " + str(created.get("type")))

            await ws.send(json.dumps(self._session_update(system_instruction, tools, model)))

            updated = await asyncio.wait_for(ws.recv(), timeout=10)
            if isinstance(updated, bytes):
                updated = updated.decode()
            update_event = json.loads(updated)
            if update_event.get("type") == "error":
                raise RuntimeError(update_event.get("error", {}).get("message", "Realtime session update error"))
            if update_event.get("type") != "session.updated":
                raise RuntimeError("Unexpected OpenAI realtime event after session.update: " + str(update_event.get("type")))

            if state.customer_transcript or state.assistant_transcript:
                await ws.send(json.dumps({
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [{
                            "type": "input_text",
                            "text":
                                "Resume this call context. Customer said: "
                                + " | ".join(state.customer_transcript[-8:])
                                + ". Assistant previously said: "
                                + " | ".join(state.assistant_transcript[-8:]),
                        }],
                    },
                }))
            return ws
        except Exception:
            try:
                await ws.close()
            except Exception:
                pass
            raise

    async def send_audio(self, session, pcm16_b64):
        await session.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": pcm16_b64,
        }))

    async def interrupt(self, session):
        try:
            await session.send(json.dumps({"type": "response.cancel"}))
            await session.send(json.dumps({"type": "output_audio_buffer.clear"}))
        except Exception:
            pass

    async def recv(self, session):
        raw = await session.recv()
        if isinstance(raw, bytes):
            raw = raw.decode()
        msg = json.loads(raw)
        typ = msg.get("type", "")

        if typ == "response.output_audio.delta":
            return {
                "serverContent": {
                    "modelTurn": {
                        "parts": [{
                            "inlineData": {
                                "mimeType": "audio/pcm;rate=24000",
                                "data": msg.get("delta", ""),
                            }
                        }]
                    }
                }
            }

        if typ in (
            "conversation.item.input_audio_transcription.completed",
            "input_audio_transcription.completed",
        ):
            return {
                "serverContent": {
                    "inputTranscription": {"text": msg.get("transcript", "")}
                }
            }

        if typ == "response.output_audio_transcript.delta":
            return {
                "serverContent": {
                    "outputTranscription": {"text": msg.get("delta", "")}
                }
            }

        if typ == "response.output_audio_transcript.done":
            return {
                "serverContent": {
                    "outputTranscription": {"text": msg.get("transcript", "")}
                }
            }

        if typ == "response.function_call_arguments.done":
            try:
                args = json.loads(msg.get("arguments") or "{}")
            except Exception:
                args = {}
            return {
                "toolCall": {
                    "functionCalls": [{
                        "id": msg.get("call_id"),
                        "name": msg.get("name"),
                        "args": args,
                    }]
                }
            }

        if typ == "response.done":
            return {"_gateway": {"event": "response_done"}}

        if typ == "input_audio_buffer.speech_started":
            return {"_gateway": {"event": "interruption"}}

        if typ == "error":
            raise RuntimeError(msg.get("error", {}).get("message", "Realtime provider error"))

        return {"_gateway": {"event": "ignored", "type": typ}}

    async def send_text(self, session, text):
        await session.send(json.dumps({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        }))
        await session.send(json.dumps({
            "type": "response.create",
            "response": {"output_modalities": ["audio"]},
        }))

    async def send_tool_response(self, session, responses):
        for r in responses:
            await session.send(json.dumps({
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": r.get("id"),
                    "output": json.dumps(r.get("response", {})),
                },
            }))
        await session.send(json.dumps({
            "type": "response.create",
            "response": {"output_modalities": ["audio"]},
        }))

    async def close(self, session):
        try:
            await session.close()
        except Exception:
            pass

class VoiceGateway:
    def __init__(self, adapters: dict[str, VoiceProviderAdapter]):
        self.adapters=adapters
    def ordered(self, providers):
        return sorted((p for p in providers if p.enabled and p.name in self.adapters),
                      key=lambda p:(p.priority,p.name))
    def adapter_for(self, provider): return self.adapters[provider.name]
    async def connect_with_failover(self, providers, *, system_instruction, tools, state):
        errors=[]
        for provider in self.ordered(providers):
            try:
                session=await self.adapter_for(provider).connect(provider,system_instruction=system_instruction,tools=tools,state=state)
                state.provider_name=provider.name
                return provider,session
            except Exception as exc:
                errors.append(provider.name+":"+str(exc))
        raise RuntimeError("No realtime voice provider available: "+"; ".join(errors))
    async def reconnect(self, providers, current_provider, *, system_instruction, tools, state):
        ordered=self.ordered(providers)
        preferred=[p for p in ordered if p.name==current_provider.name]+[p for p in ordered if p.name!=current_provider.name]
        state.reconnects += 1
        for provider in preferred:
            try:
                session=await self.adapter_for(provider).connect(provider,system_instruction=system_instruction,tools=tools,state=state)
                if provider.name!=current_provider.name: state.failovers += 1
                state.provider_name=provider.name
                return provider,session
            except Exception:
                continue
        raise RuntimeError("Realtime voice reconnect/failover exhausted")
