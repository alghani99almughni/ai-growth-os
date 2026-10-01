"""Scan main.py for public endpoints and their feature checks."""
import pathlib
import re

path = pathlib.Path("apps/api/app/main.py")
text = path.read_text(encoding="utf-8")

TARGETS = [
    "create_feedback",
    "start_public_call",
    "public_voice_ice",
    "public_voice_turn",
    "public_handoff_start",
    "public_handoff_status",
    "public_menu",
    "public_chat",
]

for fn in TARGETS:
    idx = text.find("def " + fn + "(")
    if idx < 0:
        print(f"=== {fn} === NOT FOUND")
        print()
        continue
    j = text.find("\ndef ", idx + 1)
    end = j if j > 0 else idx + 600
    body = text[idx:end]
    # Check for feature check
    has_check = "_feature_config" in body
    print(f"=== {fn} === {'? HAS CHECK' if has_check else '? NO CHECK'}")
    # Print first 15 lines
    lines = body.split("\n")[:15]
    print("\n".join(lines))
    print()