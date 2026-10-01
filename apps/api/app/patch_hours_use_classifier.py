"""Rewire intent_handlers_hours.py to use intent_patterns.py for sub-intent
detection instead of its own internal 4-language patterns."""

import pathlib

path = pathlib.Path("intent_handlers_hours.py")
text = path.read_text(encoding="utf-8")

# Marker we add so we can verify the patch went in.
MARKER = "# === CLASSIFIER-BASED SUB-INTENT DETECTION ==="

if MARKER in text:
    print("SKIP: already patched")
    raise SystemExit(0)

# Find the OLD detect_hours_subintent function and the huge
# _SUBINTENT_PATTERNS dict that precedes it. Replace both with the new
# classifier-based detector.
old_start = text.find("_SUBINTENT_PATTERNS = {")
old_end = text.find("def detect_hours_subintent", old_start)

if old_start < 0 or old_end < 0:
    print("ERROR: could not find _SUBINTENT_PATTERNS or detect_hours_subintent")
    print("  old_start:", old_start)
    print("  old_end:", old_end)
    raise SystemExit(1)

# Also locate the end of the OLD detect_hours_subintent function body.
# It ends right before the next top-level "def " or the next section marker.
# We look for "\n\n\n" followed by "# ---" or "def " after old_end.
body_search_from = old_end + len("def detect_hours_subintent")
# Find the next "\n\n\n" after the function's body
next_def = text.find("\n\ndef ", body_search_from)
next_section = text.find("\n\n# ---", body_search_from)

candidates = [x for x in (next_def, next_section) if x > 0]
if not candidates:
    print("ERROR: could not find end of detect_hours_subintent body")
    raise SystemExit(1)

old_end_full = min(candidates)

NEW_BLOCK = MARKER + '''
_SUBINTENT_MAP = {
    "business_hours_full":         "full",
    "business_hours_today":        "today",
    "business_hours_now":          "now",
    "business_hours_next_open":    "next_open",
    "business_hours_next_close":   "next_close",
    "business_hours_closed_today": "closed_today",
    "business_hours":              "default",
}


def detect_hours_subintent(message: str, language: str = "en") -> str:
    """Detect which hours-related question the customer is asking.

    Uses the shared multilingual classifier. All 11 languages are supported
    via intent_patterns.py; no per-language patterns live in this file.
    """
    try:
        from .intent_classifier import classify
    except Exception:
        return "default"
    try:
        result = classify(message or "", language)
        return _SUBINTENT_MAP.get(result.intent, "default")
    except Exception:
        return "default"
'''

text = text[:old_start] + NEW_BLOCK + text[old_end_full:]

path.write_text(text, encoding="utf-8")
print("Patched. New file size:", len(text), "bytes")