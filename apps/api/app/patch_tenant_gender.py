"""Add agent_gender column to Tenant model."""

import pathlib

path = pathlib.Path("models.py")
text = path.read_text(encoding="utf-8")

if "agent_gender" in text:
    print("SKIP: agent_gender already present")
    raise SystemExit(0)

ANCHOR = '    website: Mapped[str | None] = mapped_column(String(500), nullable=True)\n'

if ANCHOR not in text:
    print("ERROR: anchor not found")
    print("Looking for:", repr(ANCHOR))
    raise SystemExit(1)

INSERT = (
    '    agent_gender: Mapped[str] = mapped_column(String(10), default="female")\n'
)

text = text.replace(ANCHOR, ANCHOR + INSERT, 1)

path.write_text(text, encoding="utf-8")
print("Patched models.py")
print("New size:", len(text), "bytes")