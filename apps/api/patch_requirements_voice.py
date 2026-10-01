"""Add voice stack packages to requirements.txt."""

import pathlib

path = pathlib.Path("requirements.txt")
text = path.read_text(encoding="utf-8")

if "aiortc" in text:
    print("SKIP: voice packages already present")
    raise SystemExit(0)

new_lines = [
    "",
    "# Voice pipeline (Phase 4)",
    "numpy==2.1.3",
    "aiortc==1.10.0",
    "av==13.1.0",
    "vosk==0.3.45",
    "",
    "# Storage + SMS",
    "boto3==1.35.90",
    "twilio==9.4.1",
    "",
]

text = text.rstrip() + "\n" + "\n".join(new_lines) + "\n"

path.write_text(text, encoding="utf-8")
print("Patched requirements.txt")
print("New size:", len(text), "bytes")