"""Streaming Vosk STT.

Accepts PCM audio frames as they arrive from WebRTC and emits text
incrementally. Buffers up to ~5 seconds of speech, detects silence, and
returns both partial and final results.

Falls back to a stub if Vosk isn't installed so the pipeline never breaks.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


VOSK_MODEL_PATH = os.getenv("VOSK_MODEL", "models/vosk-model-small-en-us-0.15")
VOSK_SAMPLE_RATE = 16000
SILENCE_RMS_THRESHOLD = 250
SILENCE_FRAMES_TO_FLUSH = 25     # ~800ms of silence at 32ms frames


# ---------------------------------------------------------------------------
# Model cache
# ---------------------------------------------------------------------------

_MODELS = {}


def _load_model(language: str):
    if language in _MODELS:
        return _MODELS[language]

    try:
        import vosk  # type: ignore
    except Exception as exc:
        logger.info("Vosk not installed; STT will use stub: %s", exc)
        _MODELS[language] = None
        return None

    model_dir = Path(VOSK_MODEL_PATH)
    if not model_dir.exists():
        logger.info("Vosk model missing at %s", model_dir)
        _MODELS[language] = None
        return None

    try:
        vosk.SetLogLevel(-1)
        _MODELS[language] = vosk.Model(str(model_dir))
        logger.info("Vosk model loaded for %s", language)
        return _MODELS[language]
    except Exception as exc:
        logger.warning("Vosk load failed: %s", exc)
        _MODELS[language] = None
        return None


# ---------------------------------------------------------------------------
# Streaming recognizer
# ---------------------------------------------------------------------------

@dataclass
class StreamingRecognizer:
    """Buffers incoming PCM and emits text on silence or flush.

    Usage:
        stt = StreamingRecognizer(language="en")
        for chunk in audio_chunks:
            event = stt.feed(chunk)
            if event.is_final:
                handle(event.text)
        # At end of utterance:
        final_event = stt.flush()
        handle(final_event.text)
    """

    language: str = "en"
    sample_rate: int = VOSK_SAMPLE_RATE

    _rec: object = field(default=None, init=False)
    _silence_frames: int = field(default=0, init=False)
    _speaking: bool = field(default=False, init=False)
    _partial_text: str = field(default="", init=False)
    _final_text: str = field(default="", init=False)

    def __post_init__(self):
        try:
            import vosk  # type: ignore
            model = _load_model(self.language)
            if model is None:
                self._rec = None
            else:
                self._rec = vosk.KaldiRecognizer(model, self.sample_rate)
        except Exception as exc:
            logger.debug("recognizer init failed: %s", exc)
            self._rec = None

    # ------------------------------------------------------------------

    def feed(self, pcm_bytes: bytes) -> "STTEvent":
        """Feed a chunk of PCM 16-bit mono audio. Returns current state."""
        if not pcm_bytes or self._rec is None:
            return STTEvent(text="", is_final=False, is_partial=False, confidence=0.0)

        # RMS for silence detection
        try:
            import numpy as np
            samples = np.frombuffer(pcm_bytes, dtype=np.int16)
            rms = int((samples.astype(float) ** 2).mean() ** 0.5) if len(samples) else 0
        except Exception:
            rms = 0

        if rms > SILENCE_RMS_THRESHOLD:
            self._speaking = True
            self._silence_frames = 0
        elif self._speaking:
            self._silence_frames += 1

        try:
            if self._rec.AcceptWaveform(pcm_bytes):
                result = json.loads(self._rec.Result())
                text = (result.get("text") or "").strip()
                if text:
                    self._final_text = text
                    self._partial_text = ""
                    self._speaking = False
                    self._silence_frames = 0
                    return STTEvent(
                        text=text, is_final=True, is_partial=False,
                        confidence=1.0,
                    )
            else:
                partial = json.loads(self._rec.PartialResult())
                pt = (partial.get("partial") or "").strip()
                if pt != self._partial_text:
                    self._partial_text = pt
                    return STTEvent(
                        text=pt, is_final=False, is_partial=True,
                        confidence=0.5,
                    )
        except Exception as exc:
            logger.debug("stt feed failed: %s", exc)

        # Silence-triggered finalization
        if self._speaking and self._silence_frames > SILENCE_FRAMES_TO_FLUSH:
            return self.flush()

        return STTEvent(text="", is_final=False, is_partial=False, confidence=0.0)

    # ------------------------------------------------------------------

    def flush(self) -> "STTEvent":
        """Force finalization (called at end of utterance)."""
        if self._rec is None:
            return STTEvent(text="", is_final=True, is_partial=False, confidence=0.0)
        try:
            final = json.loads(self._rec.FinalResult())
            text = (final.get("text") or "").strip()
            self._speaking = False
            self._silence_frames = 0
            self._partial_text = ""
            self._final_text = ""
            return STTEvent(
                text=text, is_final=True, is_partial=False,
                confidence=1.0 if text else 0.0,
            )
        except Exception as exc:
            logger.debug("stt flush failed: %s", exc)
            return STTEvent(text="", is_final=True, is_partial=False, confidence=0.0)

    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset state for a new utterance (keeps the model)."""
        try:
            import vosk  # type: ignore
            model = _load_model(self.language)
            if model is not None:
                self._rec = vosk.KaldiRecognizer(model, self.sample_rate)
        except Exception:
            pass
        self._silence_frames = 0
        self._speaking = False
        self._partial_text = ""
        self._final_text = ""


@dataclass
class STTEvent:
    text: str
    is_final: bool
    is_partial: bool
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Convenience: transcribe a full WAV / PCM blob
# ---------------------------------------------------------------------------

def transcribe_pcm(pcm_bytes: bytes, language: str = "en", sample_rate: int = VOSK_SAMPLE_RATE) -> str:
    """One-shot transcription of complete PCM audio."""
    rec = StreamingRecognizer(language=language, sample_rate=sample_rate)
    rec.feed(pcm_bytes)
    return rec.flush().text


def is_streaming_stt_available(language: str = "en") -> bool:
    return _load_model(language) is not None