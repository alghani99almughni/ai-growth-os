"""Intent classifier.

Takes a raw message and returns the best-matching intent with a confidence
score and any entities that could be extracted.

Strategy:
1. Try the detected language's patterns first, then English.
2. Score every intent by how many of its patterns match.
3. Weight by pattern specificity (longer patterns are more specific).
4. Return the top-scoring intent, or "unknown" if confidence is too low.

This is intentionally deterministic and cheap: no model call, no database.
The router orchestrator decides what to do when confidence is low.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .intent_patterns import patterns_for, all_intents


# ---------------------------------------------------------------------------
# Language detection (script-based; not full language ID).
# ---------------------------------------------------------------------------

_SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),   # Devanagari (also Marathi, Nepali, etc.)
    "te": (0x0C00, 0x0C7F),   # Telugu
    "ta": (0x0B80, 0x0BFF),   # Tamil
    "kn": (0x0C80, 0x0CFF),   # Kannada
    "ml": (0x0D00, 0x0D7F),   # Malayalam
    "bn": (0x0980, 0x09FF),   # Bengali (also Assamese)
    "gu": (0x0A80, 0x0AFF),   # Gujarati
    "pa": (0x0A00, 0x0A7F),   # Punjabi (Gurmukhi)
    "ur": (0x0600, 0x06FF),   # Arabic (Urdu)
    "mr": (0x0900, 0x097F),   # Marathi also uses Devanagari; resolved by lexicon
}


_LEXICON_HINTS = {
    # Very common function words, used only when the script is ambiguous.
    "mr": ("काय", "कुठे", "आहे", "मला", "नाही"),
    "hi": ("क्या", "कहाँ", "है", "मुझे", "नहीं"),
    "ne": ("के", "छ", "हो", "मलाई", "तपाईं"),
}


def detect_script_language(text: str) -> str:
    """Return a BCP-47-ish language code based on the dominant Unicode script."""
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for lang, (lo, hi) in _SCRIPT_RANGES.items():
            if lo <= cp <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if not counts:
        return "en"
    winner = max(counts, key=counts.get)
    # Disambiguate Devanagari between Marathi and Hindi using a tiny lexicon.
    if winner in ("hi", "mr"):
        lowered = text.lower()
        for lang in ("mr", "hi"):
            hints = _LEXICON_HINTS.get(lang, ())
            if any(h in text or h in lowered for h in hints):
                return lang
    return winner


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    intent: str
    confidence: float
    language: str
    source: str = "pattern"           # pattern | fuzzy | default
    matches: list[str] = field(default_factory=list)
    entities: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "language": self.language,
            "source": self.source,
            "matches": self.matches,
            "entities": self.entities,
            "scores": self.scores,
        }


# ---------------------------------------------------------------------------
# Entity extraction (dates, times, quantities — language-agnostic)
# ---------------------------------------------------------------------------

_ENTITY_PATTERNS = {
    "date": re.compile(
        r"\b(today|tomorrow|yesterday|"
        r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
        r"mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)\b",
        re.IGNORECASE,
    ),
    "time": re.compile(
        r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.|o'?clock))\b",
        re.IGNORECASE,
    ),
    "quantity": re.compile(r"\b(\d+)\b"),
    "money": re.compile(r"[₹$€£]\s*\d+|\b\d+\s*(?:rupees?|rs\.?|dollars?|usd)\b", re.IGNORECASE),
    "phone": re.compile(r"\+?\d[\d\s\-]{7,}\d"),
    "yes": re.compile(r"^\s*(yes|yeah|yep|sure|ok|okay|confirm|please\s+do|go\s+ahead)\s*[.!?]?\s*$", re.IGNORECASE),
    "no": re.compile(r"^\s*(no|nope|nah|don'?t|cancel|never\s+mind|stop)\s*[.!?]?\s*$", re.IGNORECASE),
}


def extract_entities(text: str) -> dict:
    found: dict = {}
    for name, pattern in _ENTITY_PATTERNS.items():
        m = pattern.search(text)
        if m:
            found[name] = m.group(1) if m.groups() else m.group(0)
    return found


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

# Patterns below this length are treated as "weak" and given less weight.
_SPECIFICITY_FLOOR = 12
_MAX_CONFIDENCE = 1.0
_MIN_CONFIDENCE = 0.0


def _specificity(pattern: re.Pattern) -> float:
    """Longer patterns are more specific. Range: ~0.5 to 2.0."""
    length = len(pattern.pattern)
    if length <= _SPECIFICITY_FLOOR:
        return 0.5
    return min(2.0, 0.5 + (length - _SPECIFICITY_FLOOR) / 40.0)


def _score_intent(message: str, intent: str, language: str) -> tuple[float, list[str]]:
    """Score a single intent for the message.

    Returns (score, list_of_matched_pattern_strings).
    """
    patterns = patterns_for(intent, language)
    if not patterns:
        # Fall back to English if the intent has no patterns for this language.
        patterns = patterns_for(intent, "en")

    total = 0.0
    matched: list[str] = []

    for pat in patterns:
        try:
            m = pat.search(message)
        except Exception:
            continue
        if m:
            weight = _specificity(pat)
            total += weight
            matched.append(pat.pattern[:60])

    return total, matched


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Confidence thresholds. These can be tuned without changing call sites.
_CONFIDENCE_HIGH = 0.75       # use the intent confidently
_CONFIDENCE_MEDIUM = 0.40     # use the intent, but with a clarifying reply ready


def classify(message: str, language: Optional[str] = None) -> IntentResult:
    """Classify a message into an intent.

    Args:
        message: raw customer text
        language: optional BCP-47 code. If None, we detect from script.

    Returns:
        IntentResult with intent, confidence, matched patterns, and entities.
    """
    text = (message or "").strip()
    if not text:
        return IntentResult(intent="unknown", confidence=0.0, language="en",
                            source="default", entities={})

    detected = language or detect_script_language(text)

    # Score every intent for the detected language AND for English (fallback).
    raw_scores: dict[str, float] = {}
    all_matches: dict[str, list[str]] = {}

    for intent in all_intents():
        score_lang, matches_lang = _score_intent(text, intent, detected)
        if detected != "en":
            score_en, matches_en = _score_intent(text, intent, "en")
            # English patterns also count, but at half weight, so a Hindi
            # pattern beats an English one when both match.
            score = score_lang + 0.5 * score_en
            matches = matches_lang + matches_en
        else:
            score = score_lang
            matches = matches_lang
        if score > 0:
            raw_scores[intent] = score
            all_matches[intent] = matches

    entities = extract_entities(text)

    if not raw_scores:
        return IntentResult(intent="unknown", confidence=_MIN_CONFIDENCE,
                            language=detected, source="default",
                            entities=entities)

    # Winner is the highest-scoring intent.
    winner = max(raw_scores, key=raw_scores.get)
    top_score = raw_scores[winner]

    # Normalise. A single strong match on the correct language should be
    # enough to trust the intent. The pattern's specificity score already
    # accounts for how descriptive the pattern is. Divide by 1.5 so a single
    # short pattern (~0.5) reaches 0.33 and a single longer pattern (~1.0)
    # reaches ~0.67, while multiple matches push to 1.0.
    confidence = min(_MAX_CONFIDENCE, top_score / 1.5)

    # Close runner-up makes the result less certain.
    if len(raw_scores) > 1:
        runner_up = sorted(raw_scores.values(), reverse=True)[1]
        if top_score > 0 and runner_up / top_score > 0.7:
            confidence *= 0.8

    source = "pattern"

    return IntentResult(
        intent=winner,
        confidence=round(confidence, 3),
        language=detected,
        source=source,
        matches=all_matches[winner],
        entities=entities,
        scores={k: round(v, 2) for k, v in sorted(raw_scores.items(), key=lambda x: -x[1])[:5]},
    )


def classify_with_thresholds(message: str, language: Optional[str] = None) -> tuple[IntentResult, str]:
    """Convenience helper returning (result, tier).

    tier is one of: "high", "medium", "low". The router uses this to decide
    whether to trust the intent, ask for clarification, or fall back.
    """
    result = classify(message, language)
    if result.confidence >= _CONFIDENCE_HIGH:
        return result, "high"
    if result.confidence >= _CONFIDENCE_MEDIUM:
        return result, "medium"
    return result, "low"