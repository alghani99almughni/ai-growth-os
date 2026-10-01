"""Patch intent_handlers_hours.py:
1. Route 'not_configured' through AgentVoice (gender-aware).
2. Add a context passthrough to _msg().
3. Gracefully fall back for languages not in the local _MSG dict.

Does NOT touch the business-reference messages (open_until, closed_today,
today_hours etc.) - those refer to the business, not the receptionist.
"""

import pathlib

path = pathlib.Path("intent_handlers_hours.py")
text = path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# 1. Inject a context-aware _msg_context helper right after _msg definition.
# ---------------------------------------------------------------------------

_OLD_MSG_DEF = '''def _msg(lang: str, key: str, **kwargs) -> str:
    """Get a message in the given language, with format variables applied."""
    lang_msgs = _MSG.get(lang) or _MSG["en"]
    template = lang_msgs.get(key) or _MSG["en"].get(key, "")
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template'''

_NEW_MSG_DEF = '''def _msg(lang: str, key: str, **kwargs) -> str:
    """Get a message in the given language, with format variables applied.

    Only informational messages are here. Gendered receptionist messages
    (not_configured, checking_with_team, etc.) are resolved via AgentVoice.
    """
    lang_msgs = _MSG.get(lang) or _MSG["en"]
    template = lang_msgs.get(key) or _MSG["en"].get(key, "")
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


def _msg_gendered(lang: str, context: dict, key: str, **kwargs) -> str:
    """Resolve a gendered message via AgentVoice, with local fallback."""
    try:
        from .agent_voice import AgentVoice
        gender = (context or {}).get("agent_gender", "female")
        voice = AgentVoice(language=lang or "en", gender=gender)
        return voice.render(key, **kwargs)
    except Exception:
        return _msg(lang, key, **kwargs)'''

if _OLD_MSG_DEF not in text:
    print("WARNING: _msg definition not found - skipping helper injection")
else:
    text = text.replace(_OLD_MSG_DEF, _NEW_MSG_DEF, 1)
    print("Added _msg_gendered helper")

# ---------------------------------------------------------------------------
# 2. Replace the three `_msg(language, "not_configured")` calls in the main
#    handler with `_msg_gendered(language, context, "not_configured")`.
#    Only in handle_business_hours (the top-level function), not in the
#    internal _format_* helpers.
# ---------------------------------------------------------------------------

# The main handler starts at "async def handle_business_hours" and ends at
# the next top-level "async def " or end of file.
MAIN_START_MARKER = "async def handle_business_hours("
mi = text.find(MAIN_START_MARKER)
if mi < 0:
    print("WARNING: handle_business_hours not found")
else:
    mj_candidates = [
        text.find("\nasync def ", mi + 10),
        text.find("\ndef ", mi + 10),
        len(text),
    ]
    mj_candidates = [x for x in mj_candidates if x > 0]
    mj = min(mj_candidates)

    handler_block = text[mi:mj]

    # Replace only the two calls that use `language` (the handler uses `language`
    # while the format helpers use `lang`).
    old_a = 'return _msg(language, "not_configured")'
    new_a = 'return _msg_gendered(language, context, "not_configured")'
    count_a = handler_block.count(old_a)

    handler_block_new = handler_block.replace(old_a, new_a)

    # Some versions call it inside the except clause too. Same replacement.
    text = text[:mi] + handler_block_new + text[mj:]
    print(f"Updated {count_a} not_configured call(s) in handle_business_hours")

path.write_text(text, encoding="utf-8")
print("Done. New size:", len(text), "bytes")
print("_msg_gendered occurrences:", text.count("_msg_gendered"))