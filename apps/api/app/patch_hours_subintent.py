"""Patch detect_hours_subintent to strip \b from non-ASCII patterns."""

import pathlib

path = pathlib.Path("intent_handlers_hours.py")
text = path.read_text(encoding="utf-8")

OLD = '''def detect_hours_subintent(message: str, language: str = "en") -> str:
    """Detect which hours-related question the customer is asking."""
    m = (message or "").lower()
    for subintent, patterns in _SUBINTENT_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, m, re.IGNORECASE | re.UNICODE):
                return subintent
    return "default"'''

NEW = '''def _strip_unicode_unsafe_boundaries(pattern: str) -> str:
    """Python's \\b only recognises ASCII word characters, so a pattern ending
    in \\b never matches after Devanagari, Telugu, Tamil, etc. Remove the
    trailing \\b when the pattern contains non-ASCII characters."""
    try:
        pattern.encode("ascii")
        return pattern  # pure ASCII, keep as-is
    except UnicodeEncodeError:
        # Has non-ASCII characters. Strip trailing \\b and standalone \\b
        # adjacent to non-ASCII.
        if pattern.endswith(r"\\b"):
            pattern = pattern[:-2]
        if pattern.startswith(r"\\b"):
            pattern = pattern[2:]
        return pattern


def detect_hours_subintent(message: str, language: str = "en") -> str:
    """Detect which hours-related question the customer is asking."""
    m = (message or "").lower()
    for subintent, patterns in _SUBINTENT_PATTERNS.items():
        for pat in patterns:
            safe = _strip_unicode_unsafe_boundaries(pat)
            try:
                if re.search(safe, m, re.IGNORECASE | re.UNICODE):
                    return subintent
            except re.error:
                continue
    return "default"'''

if OLD not in text:
    print("ERROR: anchor not found")
    print("Looking for:")
    print(OLD[:100])
    raise SystemExit(1)

text = text.replace(OLD, NEW, 1)
path.write_text(text, encoding="utf-8")
print("Patched.")