"""Wire intent_handlers.py handlers to use AgentVoice (robust version).

Instead of matching exact return strings, this finds each handler by name
and replaces the FIRST return block that comes after 'if language ==' or
similar, right before the 'except' clause.
"""

import pathlib
import re

path = pathlib.Path("intent_handlers.py")
text = path.read_text(encoding="utf-8")

if text.count("voice.render") >= 5:
    print("SKIP: already patched")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# Mapping: handler name -> AgentVoice key
# ---------------------------------------------------------------------------
HANDLERS = {
    "handle_callback_request": "callback_logged",
    "handle_complaint":        "complaint_received",
    "handle_human_handoff":    "handoff_requested",
    "handle_refund":           "refund_forwarded",
    "handle_emergency":        "emergency_flagged",
}


def patch_handler(source: str, handler_name: str, voice_key: str) -> str:
    """Replace the multi-language return block inside the given handler
    with a voice.render call."""

    # Locate the handler
    marker = f"async def {handler_name}("
    start = source.find(marker)
    if start < 0:
        print(f"  SKIP {handler_name}: not found")
        return source

    # Find the handler's end (next top-level 'async def ' or 'def ' at col 0)
    end_candidates = [
        source.find("\nasync def ", start + len(marker)),
        source.find("\ndef ", start + len(marker)),
        len(source),
    ]
    end_candidates = [x for x in end_candidates if x > 0]
    end = min(end_candidates)

    body = source[start:end]

    # Find the LAST return statement that is NOT 'return None'
    # and that follows an 'if language ==' block.
    # We look for the pattern:
    #     if language == "hi":
    #         return "..."
    #     if language == "te":
    #         return "..."
    #     ...
    #     return "..."
    # and replace it with a voice.render call.

    # Regex: match a block starting with `if language == "hi":` and ending
    # with the last `return "..."` line before the `except` clause or next
    # top-level statement.
    # Simpler: locate 'if language == "hi":' near the end of the body and
    # find the last `return "..."` line in the body that comes after it.

    # Find the LAST occurrence of 'if language ==' in the body
    if_pos = body.rfind('if language ==')
    if if_pos < 0:
        print(f"  SKIP {handler_name}: no 'if language ==' block")
        return source

    # Find the next line that starts with `        return` after if_pos
    ret_pattern = re.compile(r"^(\s+)return\s+([\"'].*?[\"'])\s*$", re.MULTILINE)

    # From if_pos onward, find all return lines and take the range.
    section = body[if_pos:]
    matches = list(ret_pattern.finditer(section))
    if not matches:
        print(f"  SKIP {handler_name}: no return lines found after if-block")
        return source

    first_return_start = if_pos + matches[0].start()
    last_return_end = if_pos + matches[-1].end()

    # Determine indentation from the first matched return
    indent = matches[0].group(1)

    replacement = (
        f'{indent}voice = _voice_for(language, context)\n'
        f'{indent}if voice is not None:\n'
        f'{indent}    return voice.render("{voice_key}")\n'
        f'{indent}return "I\'m here to help. Please hold on a moment."'
    )

    new_body = body[:first_return_start] + replacement + body[last_return_end:]

    print(f"  PATCHED {handler_name} -> {voice_key}")

    return source[:start] + new_body + source[end:]


for handler_name, voice_key in HANDLERS.items():
    text = patch_handler(text, handler_name, voice_key)

path.write_text(text, encoding="utf-8")
print("Done. New size:", len(text), "bytes")
print("Total voice.render calls:", text.count("voice.render"))