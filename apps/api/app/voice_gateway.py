"""Provider-neutral realtime voice gateway.

Owns session state, reconnect/failover policy and provider adapter boundaries.
Business logic never talks directly to a realtime vendor.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol
import asyncio, json, time

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
    metadata: dict[str, Any] = field(default_factory=dict)

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
        url = ("wss://generativelanguage.googleapis.com/ws/"
               "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
               "?key=" + provider.api_key)
        ws = await websockets.connect(url, max_size=8*1024*1024, ping_interval=20, ping_timeout=20)
        setup = {"setup":{"model":"models/"+provider.model,
            "generationConfig":{"responseModalities":["AUDIO"]},
            "systemInstruction":{"parts":[{"text":system_instruction}]},
            "inputAudioTranscription":{},"outputAudioTranscription":{},
            "sessionResumption":{},"tools":[{"functionDeclarations":tools}]}}
        await ws.send(json.dumps(setup))
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
        return json.loads(raw)
    async def send_text(self, session, text):
        await session.send(json.dumps({"clientContent":{"turns":[{"role":"user","parts":[{"text":text}]}],"turnComplete":True}}))
    async def send_tool_response(self, session, responses):
        await session.send(json.dumps({"toolResponse":{"functionResponses":responses}}))
    async def close(self, session):
        try: await session.close()
        except Exception: pass

class OpenAIRealtimeAdapter:
    """OpenAI Realtime adapter. Messages are normalized into the gateway contract."""
    name = "openai"
    async def connect(self, provider, *, system_instruction, tools, state):
        import websockets
        url="wss://api.openai.com/v1/realtime?model="+provider.model
        ws=await websockets.connect(url, additional_headers={"Authorization":"Bearer "+provider.api_key,
            "OpenAI-Beta":"realtime=v1"}, max_size=8*1024*1024, ping_interval=20, ping_timeout=20)
        session={"type":"session.update","session":{
            "modalities":["text","audio"],"instructions":system_instruction,
            "input_audio_format":"pcm16","output_audio_format":"pcm16",
            "turn_detection":{"type":"server_vad","interrupt_response":True,"create_response":True},
            "input_audio_transcription":{"model":"gpt-4o-mini-transcribe"},
            "tools":[{"type":"function","name":t["name"],"description":t.get("description",""),
                     "parameters":t.get("parameters",{"type":"object","properties":{}})} for t in tools],
            "tool_choice":"auto"}}
        await ws.send(json.dumps(session))
        if state.customer_transcript or state.assistant_transcript:
            await ws.send(json.dumps({"type":"conversation.item.create","item":{
                "type":"message","role":"user","content":[{"type":"input_text","text":
                "Resume this call context. Customer said: "+ " | ".join(state.customer_transcript[-8:])+
                ". Assistant previously said: "+ " | ".join(state.assistant_transcript[-8:])} ]}}))
        return ws
    async def send_audio(self, session, pcm16_b64):
        await session.send(json.dumps({"type":"input_audio_buffer.append","audio":pcm16_b64}))
    async def interrupt(self, session):
        try: await session.send(json.dumps({"type":"response.cancel"}))
        except Exception: pass
    async def recv(self, session):
        raw=await session.recv()
        if isinstance(raw,bytes): raw=raw.decode()
        msg=json.loads(raw); typ=msg.get("type","")
        if typ=="response.audio.delta":
            return {"serverContent":{"modelTurn":{"parts":[{"inlineData":{"mimeType":"audio/pcm;rate=24000","data":msg.get("delta","")}}]}}}
        if typ in ("conversation.item.input_audio_transcription.completed","input_audio_transcription.completed"):
            return {"serverContent":{"inputTranscription":{"text":msg.get("transcript","")}}}
        if typ=="response.audio_transcript.delta":
            return {"serverContent":{"outputTranscription":{"text":msg.get("delta","")}}}
        if typ=="response.function_call_arguments.done":
            try: args=json.loads(msg.get("arguments") or "{}")
            except Exception: args={}
            return {"toolCall":{"functionCalls":[{"id":msg.get("call_id"),"name":msg.get("name"),"args":args}]}}
        if typ=="response.done":
            return {"_gateway":{"event":"response_done"}}
        if typ=="input_audio_buffer.speech_started":
            return {"_gateway":{"event":"interruption"}}
        if typ=="error":
            raise RuntimeError(msg.get("error",{}).get("message","Realtime provider error"))
        return {"_gateway":{"event":"ignored","type":typ}}
    async def send_text(self, session, text):
        await session.send(json.dumps({"type":"conversation.item.create","item":{"type":"message","role":"user","content":[{"type":"input_text","text":text}]}}))
        await session.send(json.dumps({"type":"response.create","response":{"modalities":["audio","text"]}}))
    async def send_tool_response(self, session, responses):
        for r in responses:
            await session.send(json.dumps({"type":"conversation.item.create","item":{
                "type":"function_call_output","call_id":r.get("id"),"output":json.dumps(r.get("response",{}))}}))
        await session.send(json.dumps({"type":"response.create","response":{"modalities":["audio","text"]}}))
    async def close(self, session):
        try: await session.close()
        except Exception: pass

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
