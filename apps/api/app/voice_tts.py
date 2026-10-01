"""Piper TTS engine.

Turns text into speech using Piper (offline, free). If Piper isn't
installed, falls back to a stub that returns silent audio.

Interface:
    synthesize(text, language, gender) -> TTSResult
    synthesize_to_wav_bytes(text, language, gender) -> bytes

Both are safe: they never raise, they always return something (silence
if nothing else is available).
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PIPER_BIN = os.getenv("PIPER_BIN", "piper")
CACHE_DIR = Path(os.getenv("TTS_CACHE_DIR", ".tts_cache"))
CACHE_ENABLED = os.getenv("TTS_CACHE", "true").lower() != "false"
CACHE_MAX_AGE_SECONDS = int(os.getenv("TTS_CACHE_MAX_AGE", "86400"))  # 1 day


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class TTSResult:
    ok: bool
    wav_bytes: bytes
    sample_rate: int
    duration_ms: int
    voice: str
    latency_ms: int
    cached: bool = False
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesize(text: str, language: str = "en", gender: str = "female") -> TTSResult:
    """Synthesize text into speech.

    Returns TTSResult. Never raises.
    """
    started = time.time()
    text = (text or "").strip()
    if not text:
        return TTSResult(
            ok=False, wav_bytes=b"", sample_rate=22050, duration_ms=0,
            voice="", latency_ms=0, error="empty_text",
        )

    from .voice_config import resolve_voice, model_path, expected_sample_rate
    voice = resolve_voice(language, gender)
    if not voice:
        return TTSResult(
            ok=False, wav_bytes=b"", sample_rate=22050, duration_ms=0,
            voice="", latency_ms=0, error="no_voice_available",
        )

    model = model_path(voice)
    if not model.exists():
        # Piper not installed locally; return silence so the pipeline works.
        logger.debug("piper model not found: %s", model)
        return TTSResult(
            ok=False, wav_bytes=b"", sample_rate=expected_sample_rate(voice),
            duration_ms=0, voice=voice, latency_ms=0, error="model_missing",
        )

    # Cache lookup
    cache_key = _cache_key(text, voice)
    if CACHE_ENABLED:
        cached = _cache_get(cache_key)
        if cached:
            return TTSResult(
                ok=True, wav_bytes=cached, sample_rate=expected_sample_rate(voice),
                duration_ms=_wav_duration_ms(cached),
                voice=voice,
                latency_ms=int((time.time() - started) * 1000),
                cached=True,
            )

    # Run Piper
    try:
        wav_bytes = _piper_synthesize(text, voice)
    except Exception as exc:
        logger.debug("piper failed: %s", exc)
        return TTSResult(
            ok=False, wav_bytes=b"", sample_rate=22050, duration_ms=0,
            voice=voice, latency_ms=int((time.time() - started) * 1000),
            error=str(exc)[:200],
        )

    if CACHE_ENABLED and wav_bytes:
        _cache_put(cache_key, wav_bytes)

    return TTSResult(
        ok=True, wav_bytes=wav_bytes, sample_rate=expected_sample_rate(voice),
        duration_ms=_wav_duration_ms(wav_bytes),
        voice=voice,
        latency_ms=int((time.time() - started) * 1000),
    )


def synthesize_to_wav_bytes(text: str, language: str = "en", gender: str = "female") -> bytes:
    """Convenience wrapper. Returns just the WAV bytes (may be empty)."""
    return synthesize(text, language, gender).wav_bytes


def is_tts_available(language: str = "en", gender: str = "female") -> bool:
    """Whether real TTS is available for this pair."""
    from .voice_config import resolve_voice, model_path
    voice = resolve_voice(language, gender)
    if not voice:
        return False
    return model_path(voice).exists()


# ---------------------------------------------------------------------------
# Piper runner
# ---------------------------------------------------------------------------

def _piper_synthesize(text: str, voice: str) -> bytes:
    """Invoke Piper CLI to synthesize text into a WAV blob."""
    from .voice_config import model_path, model_config_path

    model = model_path(voice)
    cfg = model_config_path(voice)

    out_path = tempfile.mktemp(suffix=".wav")
    try:
        cmd = [PIPER_BIN, "--model", str(model), "--output_file", out_path]
        if cfg.exists():
            cmd += ["--config", str(cfg)]

        proc = subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            capture_output=True,
            timeout=30,
        )

        if proc.returncode != 0:
            raise RuntimeError(f"piper exit {proc.returncode}: {proc.stderr[:200].decode(errors='ignore')}")

        if not Path(out_path).exists():
            raise RuntimeError("piper produced no file")

        return Path(out_path).read_bytes()
    finally:
        try:
            if Path(out_path).exists():
                os.unlink(out_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _cache_key(text: str, voice: str) -> str:
    h = hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()
    return h[:24]


def _cache_path(key: str) -> Path:
    return CACHE_DIR / key[:2] / f"{key}.wav"


def _cache_get(key: str) -> Optional[bytes]:
    try:
        p = _cache_path(key)
        if not p.exists():
            return None
        age = time.time() - p.stat().st_mtime
        if age > CACHE_MAX_AGE_SECONDS:
            p.unlink(missing_ok=True)
            return None
        return p.read_bytes()
    except Exception:
        return None


def _cache_put(key: str, data: bytes) -> None:
    try:
        p = _cache_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    except Exception as exc:
        logger.debug("cache_put failed: %s", exc)


def cleanup_cache() -> int:
    """Delete expired cache entries. Returns count removed."""
    removed = 0
    try:
        if not CACHE_DIR.exists():
            return 0
        cutoff = time.time() - CACHE_MAX_AGE_SECONDS
        for f in CACHE_DIR.rglob("*.wav"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
    except Exception as exc:
        logger.debug("cleanup_cache failed: %s", exc)
    return removed


# ---------------------------------------------------------------------------
# WAV helpers
# ---------------------------------------------------------------------------

def _wav_duration_ms(wav_bytes: bytes) -> int:
    """Read a WAV blob and return its duration in milliseconds."""
    try:
        import io
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or 1
            return int(1000 * frames / rate)
    except Exception:
        return 0