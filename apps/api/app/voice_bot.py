"""Server-side WebRTC voice bot.

Acts as the AI receptionist in a WebRTC call with a customer. Bridges:
    Customer audio (WebRTC) -> Streaming STT -> Orchestrator -> TTS -> WebRTC back

Design:
    - Uses aiortc for WebRTC
    - Uses Vosk (voice_stt) for STT
    - Uses Piper (voice_tts) for TTS
    - Never raises: any internal error produces a graceful fallback reply
    - Records every turn via CallRecorder (for QA + diagnostics)

Usage:
    bot = VoiceBot(db, tenant, call_record_id=call.id, ...)
    answer = await bot.create_answer(offer_sdp)
    # answer is a JSON dict {sdp, type} to send back to the browser
"""
from __future__ import annotations

import asyncio
import fractions
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None
    _NUMPY_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional imports — aiortc may not be installed locally
# ---------------------------------------------------------------------------

try:
    from aiortc import (
        RTCPeerConnection,
        RTCSessionDescription,
        MediaStreamTrack,
    )
    from av import AudioFrame
    _AIORTC_AVAILABLE = True
except Exception:
    _AIORTC_AVAILABLE = False
    logger.info("aiortc not installed; voice bot will run in stub mode")


# ---------------------------------------------------------------------------
# TTS Audio Track — feeds synthesized speech into WebRTC
# ---------------------------------------------------------------------------

if _AIORTC_AVAILABLE and _NUMPY_AVAILABLE:
    class TTSAudioTrack(MediaStreamTrack):
        kind = "audio"

        def __init__(self, sample_rate: int = 48000):
            super().__init__()
            self.sample_rate = sample_rate
            self._queue: asyncio.Queue = asyncio.Queue()
            self._pts = 0

        async def add_speech_wav(self, wav_bytes: bytes, source_rate: int = 22050):
            """Decode WAV bytes, resample to 48k, enqueue PCM frames."""
            try:
                import io
                import wave

                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    src_rate = wf.getframerate()
                    pcm = wf.readframes(wf.getnframes())

                samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

                if src_rate != self.sample_rate:
                    ratio = self.sample_rate / src_rate
                    new_len = int(len(samples) * ratio)
                    idx = np.linspace(0, len(samples) - 1, new_len)
                    samples = np.interp(idx, np.arange(len(samples)), samples).astype(np.float32)

                chunk = 960  # 20ms at 48k
                for i in range(0, len(samples), chunk):
                    block = samples[i:i + chunk]
                    if len(block) < chunk:
                        block = np.pad(block, (0, chunk - len(block)))
                    await self._queue.put(block)

                # Trailing silence so caller knows we stopped talking
                await self._queue.put(np.zeros(chunk, dtype=np.float32))
            except Exception as exc:
                logger.debug("add_speech_wav failed: %s", exc)

        async def recv(self):
            try:
                samples = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                samples = np.zeros(960, dtype=np.float32)

            pcm16 = (samples * 32767).astype(np.int16)
            frame = AudioFrame.from_ndarray(
                pcm16.reshape(1, -1), format="s16", layout="mono"
            )
            frame.sample_rate = self.sample_rate
            frame.pts = self._pts
            frame.time_base = fractions.Fraction(1, self.sample_rate)
            self._pts += len(pcm16)
            return frame


# ---------------------------------------------------------------------------
# VoiceBot
# ---------------------------------------------------------------------------

@dataclass
class VoiceBotConfig:
    language: str = "en"
    gender: str = "female"
    greeting: str = "Hello, how can I help you today?"
    silence_ms_to_flush: int = 800


class VoiceBot:
    """One per WebRTC call. Manages the peer, STT, orchestrator, TTS."""

    def __init__(
        self,
        db,
        tenant,
        *,
        customer=None,
        call_record_id: Optional[str] = None,
        config: Optional[VoiceBotConfig] = None,
    ):
        self.db = db
        self.tenant = tenant
        self.customer = customer
        self.call_record_id = call_record_id
        self.config = config or VoiceBotConfig()

        self.pc = None
        self.recorder = None
        self.recognizer = None
        self.tts_track = None
        self._closed = False
        self._busy = False

        # Runtime state
        self._lang = self.config.language
        self._gender = getattr(tenant, "agent_gender", "female") or "female"
        self._conversation_id = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_answer(self, offer_sdp: str, offer_type: str = "offer") -> dict:
        """Accept a WebRTC offer and return our answer."""
        if not _AIORTC_AVAILABLE:
            logger.info("voice_bot: aiortc unavailable, returning stub answer")
            return {"type": "answer", "sdp": "", "error": "webrtc_unavailable"}

        try:
            # Initialize recorder
            try:
                from .call_recorder import CallRecorder
                self.recorder = CallRecorder(
                    self.db, self.tenant.id,
                    customer_id=getattr(self.customer, "id", None) if self.customer else None,
                    customer_name=getattr(self.customer, "name", "Guest") if self.customer else "Guest",
                    customer_phone=getattr(self.customer, "mobile", "") if self.customer else "",
                    channel="webrtc_bot",
                    language=self._lang,
                    call_record_id=self.call_record_id,
                )
                self.recorder.start()
            except Exception as exc:
                logger.debug("recorder init failed: %s", exc)
                self.recorder = None

            # Initialize STT
            try:
                from .voice_stt import StreamingRecognizer
                self.recognizer = StreamingRecognizer(language=self._lang)
            except Exception as exc:
                logger.debug("stt init failed: %s", exc)
                self.recognizer = None

            # Create peer
            self.pc = RTCPeerConnection()
            self.tts_track = TTSAudioTrack()
            self.pc.addTrack(self.tts_track)
            self.pc.on("track", self._on_track)
            self.pc.on("connectionstatechange", self._on_state)

            # Set offer, create answer
            offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)
            await self.pc.setRemoteDescription(offer)
            answer = await self.pc.createAnswer()
            await self.pc.setLocalDescription(answer)

            # Greet the customer
            asyncio.create_task(self._greet())

            return {
                "type": "answer",
                "sdp": self.pc.localDescription.sdp,
                "call_id": self.call_record_id,
            }
        except Exception as exc:
            logger.exception("create_answer failed: %s", exc)
            return {"type": "answer", "sdp": "", "error": str(exc)[:200]}

    async def close(self):
        """Cleanly close the bot."""
        self._closed = True
        try:
            if self.recorder:
                self.recorder.finish()
        except Exception:
            pass
        try:
            if self.pc:
                await self.pc.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # WebRTC handlers
    # ------------------------------------------------------------------

    def _on_state(self):
        try:
            state = self.pc.connectionState
            logger.info("voice_bot state: %s", state)
            if state in ("failed", "closed", "disconnected") and not self._closed:
                asyncio.create_task(self.close())
        except Exception:
            pass

    def _on_track(self, track):
        if track.kind == "audio":
            asyncio.ensure_future(self._consume_audio(track))

    async def _consume_audio(self, track):
        while not self._closed:
            try:
                frame = await track.recv()
            except Exception:
                break

            try:
                pcm = self._frame_to_pcm(frame)
                if pcm is None:
                    continue
                await self._process_audio_chunk(pcm)
            except Exception as exc:
                logger.debug("audio consume failed: %s", exc)

    def _frame_to_pcm(self, frame) -> Optional[bytes]:
        """Convert an aiortc AudioFrame to 16k mono PCM bytes."""
        try:
            arr = frame.to_ndarray()
            pcm = arr.reshape(-1).astype(np.int16)
            if frame.sample_rate == 48000:
                pcm = pcm[::3]  # 48k -> 16k
            elif frame.sample_rate != 16000:
                ratio = 16000 / frame.sample_rate
                new_len = int(len(pcm) * ratio)
                idx = np.linspace(0, len(pcm) - 1, new_len)
                pcm = np.interp(idx, np.arange(len(pcm)), pcm).astype(np.int16)
            return pcm.tobytes()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Turn processing
    # ------------------------------------------------------------------

    async def _process_audio_chunk(self, pcm: bytes):
        if self.recognizer is None or self._busy:
            return

        try:
            event = self.recognizer.feed(pcm)
        except Exception:
            return

        if not event.is_final or not event.text.strip():
            return

        # We have a final utterance — process it
        text = event.text.strip()
        self.recognizer.reset()
        await self._handle_utterance(text)

    async def _handle_utterance(self, text: str):
        if self._busy:
            return
        self._busy = True
        try:
            if self.recorder:
                self.recorder.begin_turn()
                self.recorder.capture_customer(text=text)

            # Run the orchestrator
            from .router_orchestrator import route_message
            result = await route_message(
                self.db,
                self.tenant,
                self.customer,
                text,
                conversation_id=self._conversation_id,
                channel="webrtc_bot",
            )
            self._conversation_id = result.conversation_id or self._conversation_id

            # Update language if classifier detected a change
            if result.language and result.language != self._lang:
                self._lang = result.language
                if self.recorder:
                    self.recorder.language_end = self._lang
                try:
                    from .voice_stt import StreamingRecognizer
                    self.recognizer = StreamingRecognizer(language=self._lang)
                except Exception:
                    pass

            # Synthesize the reply
            wav_bytes = b""
            try:
                from .voice_tts import synthesize
                tts = synthesize(result.reply, self._lang, self._gender)
                wav_bytes = tts.wav_bytes
                if wav_bytes and self.tts_track is not None:
                    await self.tts_track.add_speech_wav(wav_bytes, tts.sample_rate)
            except Exception as exc:
                logger.debug("tts failed: %s", exc)

            # Record the turn
            if self.recorder:
                self.recorder.capture_ai(text=result.reply, audio_bytes=wav_bytes)
                self.recorder.annotate_turn(
                    intent=result.intent,
                    confidence=result.confidence,
                    language=result.language,
                    source=result.source,
                    handler_name=result.handler,
                    handler_succeeded=(result.source == "handler"),
                    tokens_used=result.tokens_used,
                    cost_usd=result.cost_usd,
                )
        except Exception as exc:
            logger.exception("handle_utterance failed: %s", exc)
        finally:
            self._busy = False

    # ------------------------------------------------------------------
    # Greeting
    # ------------------------------------------------------------------

    async def _greet(self):
        try:
            greeting = self.config.greeting
            wav_bytes = b""
            try:
                from .voice_tts import synthesize
                tts = synthesize(greeting, self._lang, self._gender)
                wav_bytes = tts.wav_bytes
                if wav_bytes and self.tts_track is not None:
                    await self.tts_track.add_speech_wav(wav_bytes, tts.sample_rate)
            except Exception as exc:
                logger.debug("greeting tts failed: %s", exc)

            if self.recorder:
                self.recorder.begin_turn()
                self.recorder.capture_customer(text="")
                self.recorder.capture_ai(text=greeting, audio_bytes=wav_bytes)
                self.recorder.annotate_turn(
                    intent="greeting",
                    confidence=1.0,
                    language=self._lang,
                    source="greeting",
                )
        except Exception as exc:
            logger.debug("greet failed: %s", exc)


# ---------------------------------------------------------------------------
# Convenience: create a bot with default settings for a tenant + call
# ---------------------------------------------------------------------------

def make_bot(db, tenant, call_record_id=None, customer=None, language="en") -> VoiceBot:
    """Factory. Picks up tenant gender automatically."""
    cfg = VoiceBotConfig(language=language)
    return VoiceBot(
        db, tenant,
        customer=customer,
        call_record_id=call_record_id,
        config=cfg,
    )


def is_voice_bot_available() -> bool:
    """Whether real WebRTC (aiortc) is available in this environment."""
    return _AIORTC_AVAILABLE