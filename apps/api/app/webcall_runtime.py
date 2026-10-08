from __future__ import annotations

import asyncio
import base64
import logging
import time
from fractions import Fraction
from typing import Any

from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack
from aiortc.sdp import candidate_from_sdp
from av import AudioFrame
from av.audio.resampler import AudioResampler
from fastapi import WebSocket
from starlette.websockets import WebSocketState

from .voice_gateway import VoiceGateway, VoiceProvider, VoiceSessionState
from .voice_crosscheck import crosscheck_turn, crosscheck_payload

logger = logging.getLogger("uvicorn.error")

AUDIO_RATE = 24000
FRAME_MS = 20
SAMPLES_PER_FRAME = AUDIO_RATE * FRAME_MS // 1000
BYTES_PER_SAMPLE = 2
SILENCE_FRAME_BYTES = SAMPLES_PER_FRAME * BYTES_PER_SAMPLE


class PcmAudioTrack:
    """Small deterministic PCM framing helper used by the WebRTC runtime."""

    def __init__(self, sample_rate: int = AUDIO_RATE, frame_ms: int = FRAME_MS):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.samples = sample_rate * frame_ms // 1000
        self.buffer = bytearray()

    def feed(self, pcm: bytes) -> list[bytes]:
        self.buffer.extend(pcm)
        size = self.samples * BYTES_PER_SAMPLE
        out: list[bytes] = []
        while len(self.buffer) >= size:
            out.append(bytes(self.buffer[:size]))
            del self.buffer[:size]
        return out


class OutgoingAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=80)
        self.pts = 0
        self.closed = False
        self._framer = PcmAudioTrack()

    async def recv(self) -> AudioFrame:
        try:
            pcm = await asyncio.wait_for(self.queue.get(), timeout=FRAME_MS / 1000 * 2)
        except asyncio.TimeoutError:
            pcm = b"\x00" * SILENCE_FRAME_BYTES
        if pcm is None:
            self.closed = True
            pcm = b"\x00" * SILENCE_FRAME_BYTES
        if len(pcm) < SILENCE_FRAME_BYTES:
            pcm += b"\x00" * (SILENCE_FRAME_BYTES - len(pcm))
        elif len(pcm) > SILENCE_FRAME_BYTES:
            pcm = pcm[:SILENCE_FRAME_BYTES]
        frame = AudioFrame(format="s16", layout="mono", samples=SAMPLES_PER_FRAME)
        frame.sample_rate = AUDIO_RATE
        frame.time_base = Fraction(1, AUDIO_RATE)
        frame.pts = self.pts
        self.pts += SAMPLES_PER_FRAME
        frame.planes[0].update(pcm)
        return frame

    async def push_pcm(self, pcm: bytes) -> None:
        if self.closed:
            return
        for chunk in self._framer.feed(pcm):
            try:
                self.queue.put_nowait(chunk)
            except asyncio.QueueFull:
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    self.queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

    def clear(self) -> None:
        while True:
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def close(self) -> None:
        self.closed = True
        self.clear()
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            pass


class WebCallRuntime:
    """Dograh-inspired WebRTC media bridge around our existing voice gateway.

    Browser audio never talks directly to the model. WebRTC terminates here,
    the existing provider adapter remains responsible for realtime AI, and
    Knowledge Brain V2 is cross-checked on every finalized customer turn.
    """

    def __init__(self, websocket: WebSocket, call_id: str, providers: list[VoiceProvider], system_instruction: str):
        self.websocket = websocket
        self.call_id = call_id
        self.providers = providers
        self.system_instruction = system_instruction
        self.pc = RTCPeerConnection()
        self.outgoing = OutgoingAudioTrack()
        self.incoming_task: asyncio.Task | None = None
        self.provider_task: asyncio.Task | None = None
        self.stats_task: asyncio.Task | None = None
        self.provider = None
        self.session = None
        self.gateway = VoiceGateway({})
        self.state = VoiceSessionState(call_id=call_id, provider_name="")
        self.closed = False
        self.last_customer_activity = time.monotonic()
        self._resampler = AudioResampler(format="s16", layout="mono", rate=16000)
        self._last_stats_signature = ""

    async def send(self, payload: dict[str, Any]) -> None:
        if self.websocket.application_state == WebSocketState.CONNECTED:
            await self.websocket.send_json(payload)

    @staticmethod
    def _has_speech_energy(pcm: bytes, threshold: int = 500) -> bool:
        """Reject continuous microphone silence/noise from resetting inactivity timeout."""
        if len(pcm) < 4:
            return False
        samples = memoryview(pcm).cast("h")
        if not samples:
            return False
        mean_abs = sum(abs(int(x)) for x in samples) / len(samples)
        return mean_abs >= threshold

    async def _stats_loop(self) -> None:
        while not self.closed:
            try:
                stats = await self.pc.getStats()
                for item in stats.values():
                    if item.type != "candidate-pair" or getattr(item, "state", "") != "succeeded":
                        continue

                    local_id = getattr(item, "localCandidateId", None)
                    remote_id = getattr(item, "remoteCandidateId", None)
                    local_candidate = stats.get(local_id) if local_id else None
                    remote_candidate = stats.get(remote_id) if remote_id else None

                    local_type = (
                        getattr(local_candidate, "candidateType", "unknown")
                        if local_candidate else "unknown"
                    )
                    remote_type = (
                        getattr(remote_candidate, "candidateType", "unknown")
                        if remote_candidate else "unknown"
                    )

                    signature = (
                        "|".join(
                            str(getattr(item, k, ""))
                            for k in (
                                "localCandidateId",
                                "remoteCandidateId",
                                "currentRoundTripTime",
                                "bytesSent",
                                "bytesReceived",
                            )
                        )
                        + f"|{local_type}|{remote_type}"
                    )

                    if signature != self._last_stats_signature:
                        self._last_stats_signature = signature

                        if "relay" in {local_type, remote_type}:
                            path = "relay"
                        elif "srflx" in {local_type, remote_type}:
                            path = "srflx"
                        else:
                            path = "host"

                        await self.send({
                            "type": "diagnostic",
                            "event": "ice_candidate_pair",
                            "local_candidate_id": local_id,
                            "remote_candidate_id": remote_id,
                            "local_candidate_type": local_type,
                            "remote_candidate_type": remote_type,
                            "path": path,
                            "rtt_ms": round(
                                float(
                                    getattr(item, "currentRoundTripTime", 0) or 0
                                ) * 1000,
                                2,
                            ),
                            "bytes_sent": getattr(item, "bytesSent", 0),
                            "bytes_received": getattr(item, "bytesReceived", 0),
                        })

            except asyncio.CancelledError:
                return
            except Exception as exc:
                if not self.closed:
                    logger.debug(
                        "WEB_CALL_STATS_FAILED call_id=%s error=%s",
                        self.call_id,
                        str(exc)[:160],
                    )

            await asyncio.sleep(2)

    async def setup_peer(self, offer: dict[str, Any]) -> None:
        self.pc.addTrack(self.outgoing)

        @self.pc.on("track")
        def on_track(track):
            logger.info("WEB_CALL_TRACK call_id=%s kind=%s", self.call_id, track.kind)
            if track.kind == "audio":
                self.incoming_task = asyncio.create_task(self.consume_microphone(track))

        @self.pc.on("iceconnectionstatechange")
        async def on_ice_state():
            logger.info("WEB_CALL_ICE_STATE call_id=%s state=%s", self.call_id, self.pc.iceConnectionState)
            await self.send({"type": "ice_state", "state": self.pc.iceConnectionState})

        @self.pc.on("connectionstatechange")
        async def on_state():
            logger.info("WEB_CALL_PC_STATE call_id=%s state=%s", self.call_id, self.pc.connectionState)
            await self.send({"type": "pc_state", "state": self.pc.connectionState})
            if self.pc.connectionState in {"failed", "closed"}:
                self.closed = True

        await self.pc.setRemoteDescription(
            RTCSessionDescription(sdp=offer["sdp"], type=offer.get("sdp_type", "offer"))
        )
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        deadline = time.monotonic() + 5
        while self.pc.iceGatheringState != "complete" and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        local = self.pc.localDescription
        await self.send({"type": "answer", "sdp": local.sdp, "sdp_type": local.type})
        self.stats_task = asyncio.create_task(self._stats_loop())

    async def add_remote_candidate(self, payload: dict[str, Any]) -> None:
        candidate = payload.get("candidate") if isinstance(payload, dict) else None
        if not candidate:
            return
        candidate_text = candidate.get("candidate", "") if isinstance(candidate, dict) else str(candidate)
        if not candidate_text:
            return
        parsed = candidate_from_sdp(candidate_text)
        parsed.sdpMid = candidate.get("sdpMid") if isinstance(candidate, dict) else None
        parsed.sdpMLineIndex = candidate.get("sdpMLineIndex") if isinstance(candidate, dict) else None
        await self.pc.addIceCandidate(parsed)

    async def consume_microphone(self, track) -> None:
        while not self.closed:
            try:
                frame = await track.recv()
                frames = self._resampler.resample(frame)
                for resampled in frames:
                    pcm = bytes(resampled.planes[0])
                    if self.provider and self.session:
                        await self.gateway.adapter_for(self.provider).send_audio(
                            self.session, base64.b64encode(pcm).decode("ascii")
                        )
                        if self._has_speech_energy(pcm):
                            self.last_customer_activity = time.monotonic()
            except Exception as exc:
                if not self.closed:
                    logger.info("WEB_CALL_MIC_STOP call_id=%s error=%s", self.call_id, str(exc)[:180])
                return

    async def provider_loop(self) -> None:
        while not self.closed:
            try:
                adapter = self.gateway.adapter_for(self.provider)
                event = await adapter.recv(self.session)
            except Exception as exc:
                if self.closed:
                    return
                old = self.provider
                try:
                    self.provider, self.session = await self.gateway.reconnect(
                        self.providers,
                        old,
                        system_instruction=self.system_instruction,
                        tools=[],
                        state=self.state,
                    )
                    self.outgoing.clear()
                    await self.send({
                        "type": "status",
                        "status": "ai_reconnected",
                        "provider": self.provider.name,
                        "reconnects": self.state.reconnects,
                        "failovers": self.state.failovers,
                    })
                    continue
                except Exception as reconnect_exc:
                    logger.exception(
                        "WEB_CALL_PROVIDER_RECONNECT_FAILED call_id=%s error=%s",
                        self.call_id, str(reconnect_exc)[:220],
                    )
                    await self.send({"type": "error", "code": "ai_provider_reconnect_failed", "recoverable": True})
                    self.closed = True
                    return

            gw = event.get("_gateway") or {}
            if gw.get("event") == "interruption":
                self.outgoing.clear()
                await self.send({"type": "interruption"})
                continue

            sc = event.get("serverContent") or {}
            inp = (sc.get("inputTranscription") or {}).get("text")
            out = (sc.get("outputTranscription") or {}).get("text")

            if inp:
                self.last_customer_activity = time.monotonic()
                result = crosscheck_turn(inp, "generic")
                await self.send({
                    "type": "transcript",
                    "role": "customer",
                    "text": inp,
                    "crosscheck": crosscheck_payload(result),
                })
            if out:
                await self.send({"type": "transcript", "role": "ai", "text": out})

            parts = ((sc.get("modelTurn") or {}).get("parts") or [])
            for part in parts:
                data = (part.get("inlineData") or {}).get("data")
                if data:
                    await self.outgoing.push_pcm(base64.b64decode(data))

            if event.get("toolCall"):
                await self.send({
                    "type": "diagnostic",
                    "event": "tool_call_received",
                    "tool_count": len(event["toolCall"].get("functionCalls", [])),
                })

    async def close(self) -> None:
        if self.closed and self.pc.connectionState == "closed":
            return
        self.closed = True
        for task in (self.incoming_task, self.provider_task, self.stats_task):
            if task:
                task.cancel()
        try:
            if self.provider and self.session:
                await self.gateway.adapter_for(self.provider).close(self.session)
        except Exception:
            pass
        try:
            await self.outgoing.close()
        except Exception:
            pass
        try:
            await self.pc.close()
        except Exception:
            pass


async def wait_for_ice_timeout(runtime: WebCallRuntime, timeout: float = 60.0) -> None:
    while not runtime.closed:
        await asyncio.sleep(2)
        if time.monotonic() - runtime.last_customer_activity > timeout:
            await runtime.send({"type": "timeout", "reason": "customer_inactive"})
            await runtime.close()
            return
