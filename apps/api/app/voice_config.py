"""Voice configuration.

Maps (language, gender) -> Piper TTS voice model path.

When a language has no voice for the requested gender, we fall back in
this order:
    1. Exact match (language + gender)
    2. Same language, opposite gender (better than silence)
    3. English, same gender
    4. English, female (default)

All model paths are relative to PIPER_MODELS_DIR.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


PIPER_MODELS_DIR = Path(os.getenv("PIPER_MODELS_DIR", "models/piper"))
PIPER_BIN = os.getenv("PIPER_BIN", "piper")


# ---------------------------------------------------------------------------
# Voice registry
# Format: VOICES[language][gender] = filename (without .onnx)
# ---------------------------------------------------------------------------

VOICES = {
    "en": {
        "female": "en_US-lessac-medium",
        "male":   "en_US-ryan-medium",
    },
    "hi": {
        "female": "hi_IN-swara-medium",
        "male":   "hi_IN-pratham-medium",
    },
    "te": {
        "female": "te_IN-...",  # placeholder until a voice is added
        "male":   "te_IN-...",
    },
    "ta": {
        "female": "ta_IN-...",
        "male":   "ta_IN-...",
    },
    "kn": {
        "female": "kn_IN-...",
        "male":   "kn_IN-...",
    },
    "ml": {
        "female": "ml_IN-...",
        "male":   "ml_IN-...",
    },
    "mr": {
        "female": "mr_IN-...",
        "male":   "mr_IN-...",
    },
    "bn": {
        "female": "bn_IN-...",
        "male":   "bn_IN-...",
    },
    "gu": {
        "female": "gu_IN-...",
        "male":   "gu_IN-...",
    },
    "pa": {
        "female": "pa_IN-...",
        "male":   "pa_IN-...",
    },
    "ur": {
        "female": "ur_PK-...",
        "male":   "ur_PK-...",
    },
}


# ---------------------------------------------------------------------------
# Fallback chain
# ---------------------------------------------------------------------------

def resolve_voice(language: str, gender: str) -> Optional[str]:
    """Return the Piper model name for the (language, gender) pair.

    Walks the fallback chain. Returns None if no voice is available at all.
    """
    lang = (language or "en").lower()
    gen = (gender or "female").lower()

    # 1. Exact match
    entry = VOICES.get(lang, {})
    voice = entry.get(gen) or entry.get("female")
    if _is_valid_voice(voice):
        return voice

    # 2. Same language, opposite gender
    other_gen = "male" if gen == "female" else "female"
    voice = entry.get(other_gen)
    if _is_valid_voice(voice):
        logger.info("voice fallback: %s/%s -> %s/%s (same lang, other gender)",
                    lang, gen, lang, other_gen)
        return voice

    # 3. English same gender
    en_entry = VOICES.get("en", {})
    voice = en_entry.get(gen)
    if _is_valid_voice(voice):
        logger.info("voice fallback: %s/%s -> en/%s", lang, gen, gen)
        return voice

    # 4. English female
    voice = en_entry.get("female")
    if _is_valid_voice(voice):
        logger.info("voice fallback: %s/%s -> en/female", lang, gen)
        return voice

    return None


def _is_valid_voice(voice: Optional[str]) -> bool:
    """Voice names ending in '...' are placeholders. Skip them."""
    if not voice:
        return False
    if voice.endswith("..."):
        return False
    return True


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def model_path(voice_name: str) -> Path:
    """Return the full path to the .onnx model file."""
    return PIPER_MODELS_DIR / f"{voice_name}.onnx"


def model_config_path(voice_name: str) -> Path:
    """Return the full path to the .onnx.json config."""
    return PIPER_MODELS_DIR / f"{voice_name}.onnx.json"


def voice_available(language: str, gender: str) -> bool:
    """Whether a real voice is available for this pair on disk."""
    name = resolve_voice(language, gender)
    if not name:
        return False
    return model_path(name).exists()


def list_available_voices() -> list:
    """Return a list of (language, gender, model_name, present_on_disk)."""
    result = []
    for lang, by_gender in VOICES.items():
        for gender, name in by_gender.items():
            result.append({
                "language": lang,
                "gender": gender,
                "model": name,
                "on_disk": model_path(name).exists() if not name.endswith("...") else False,
            })
    return result


# ---------------------------------------------------------------------------
# Sample rate
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22050  # Piper default output rate


def expected_sample_rate(voice_name: str) -> int:
    """Piper voices output at various rates. Try to read the config."""
    try:
        import json
        cfg_path = model_config_path(voice_name)
        if cfg_path.exists():
            cfg = json.loads(cfg_path.read_text())
            return int(cfg.get("audio", {}).get("sample_rate", SAMPLE_RATE))
    except Exception:
        pass
    return SAMPLE_RATE