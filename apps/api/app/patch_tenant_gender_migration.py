"""Add agent_gender column migration to migrations.py."""

import pathlib

path = pathlib.Path("migrations.py")
text = path.read_text(encoding="utf-8")

if "agent_gender" in text:
    print("SKIP: agent_gender migration already present")
    raise SystemExit(0)

ANCHOR = (
    '            conn.execute(text("ALTER TABLE tenants '
    'ADD COLUMN IF NOT EXISTS status VARCHAR(30) DEFAULT \'active\'"))\n'
)

if ANCHOR not in text:
    print("ERROR: anchor not found")
    print("Looking for:", repr(ANCHOR))
    raise SystemExit(1)

INSERT = (
    '            conn.execute(text("ALTER TABLE tenants '
    'ADD COLUMN IF NOT EXISTS agent_gender VARCHAR(10) DEFAULT \'female\'"))\n'
)

text = text.replace(ANCHOR, ANCHOR + INSERT, 1)

path.write_text(text, encoding="utf-8")
print("Patched migrations.py")
print("New size:", len(text), "bytes")