"""Offline speech-to-text.

Transcribes buffered audio blobs from offline calls. Uses Vosk (offline,
free) if installed. If Vosk is unavailable, falls back to a stub so the
rest of the pipeline never breaks.

Design:
    - Load the model once at import (lazy on first use)
    - Accept raw bytes (WebM/Opus, WAV, MP4)
    - Convert to 16kHz mono PCM internally
    - Return plain text
"""
from __future__ import annotations

import io
import logging
import os
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

VOSK_MODEL_PATH = os.getenv("VOSK_MODEL", "models/vosk-model-small-en-us-0.15")
FFMPEG_BIN = os.getenv("FFMPEG_BIN", "ffmpeg")

_vosk_model = None
_vosk_loaded = False


# ---------------------------------------------------------------------------
# Model loading (lazy)
# ---------------------------------------------------------------------------

def _load_model():
    """Load Vosk model on first use. Returns None if unavailable."""
    global _vosk_model, _vosk_loaded
    if _vosk_loaded:
        return _vosk_model
    _vosk_loaded = True

    try:
        import vosk  # type: ignore
    except Exception as exc:
        logger.info("Vosk not installed; STT will use stub: %s", exc)
        return None

    model_dir = Path(VOSK_MODEL_PATH)
    if not model_dir.exists():
        logger.info("Vosk model not found at %s; using stub", VOSK_MODEL_PATH)
        return None

    try:
        vosk.SetLogLevel(-1)  # quiet
        _vosk_model = vosk.Model(str(model_dir))
        logger.info("Vosk model loaded: %s", VOSK_MODEL_PATH)
        return _vosk_model
    except Exception as exc:
        logger.warning("Vosk model load failed: %s", exc)
        _vosk_model = None
        return None


# ---------------------------------------------------------------------------
# Audio conversion
# ---------------------------------------------------------------------------

def _to_pcm_16k_mono_wav(audio_bytes: bytes) -> Optional[bytes]:
    """Convert arbitrary audio bytes to 16kHz mono PCM WAV.

    Uses ffmpeg if available. Returns WAV bytes or None.
    """
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as fin:
            fin.write(audio_bytes)
            in_path = fin.name
        out_path = in_path + ".wav"

        result = subprocess.run(
            [
                FFMPEG_BIN, "-y", "-loglevel", "error",
                "-i", in_path,
                "-ar", "16000", "-ac", "1",
                "-f", "wav", out_path,
            ],
            capture_output=True,
            timeout=60,
        )

        try:
            os.unlink(in_path)
        except Exception:
            pass

        if result.returncode != 0:
            logger.debug("ffmpeg failed: %s", result.stderr[:200])
            try:
                os.unlink(out_path)
            except Exception:
                pass
            return None

        data = Path(out_path).read_bytes()
        try:
            os.unlink(out_path)
        except Exception:
            pass
        return data
    except FileNotFoundError:
        logger.debug("ffmpeg not found; STT unavailable")
        return None
    except Exception as exc:
        logger.debug("audio conversion failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Vosk transcription
# ---------------------------------------------------------------------------

def _transcribe_vosk(wav_bytes: bytes, language: str = "en") -> Optional[str]:
    """Run Vosk on 16kHz mono PCM WAV bytes. Returns text or None."""
    model = _load_model()
    if model is None:
        return None

    try:
        import json
        import vosk  # type: ignore

        wf = wave.open(io.BytesIO(wav_bytes), "rb")
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            logger.debug("wav not mono 16-bit; skipping vosk")
            return None

        rec = vosk.KaldiRecognizer(model, wf.getframerate())
        text_parts = []
        while True:
            data = wf.readframes(4000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                if result.get("text"):
                    text_parts.append(result["text"])

        final = json.loads(rec.FinalResult())
        if final.get("text"):
            text_parts.append(final["text"])

        return " ".join(text_parts).strip()
    except Exception as exc:
        logger.debug("vosk transcribe failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def transcribe(
    audio_bytes: bytes,
    language: str = "en",
    *,
    stub_text: Optional[str] = None,
) -> str:
    """Transcribe audio bytes into text.

    Fallback chain:
        1. Vosk (if installed and model present)
        2. stub_text (if provided by the caller)
        3. "" (empty string)

    Never raises.
    """
    if not audio_bytes:
        return stub_text or ""

    wav = _to_pcm_16k_mono_wav(audio_bytes)
    if wav is None:
        return stub_text or ""

    text = _transcribe_vosk(wav, language)
    if text:
        return text

    return stub_text or ""


def is_stt_available() -> bool:
    """Whether real STT is available (Vosk + model loaded)."""
    return _load_model() is not None