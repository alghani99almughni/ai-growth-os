"""Fix Session 9 - remove the broken add_loyalty definition.

The Session 9 patcher inserted a new add_loyalty that referenced a
non-existent Pydantic model (LoyaltyCreate). This removes that broken
block so the file imports cleanly again.

Run from apps/api:
    python fix_session9.py
"""
import pathlib
import sys
import re

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: app/main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

# The broken block starts with the decorator we inserted and ends at the
# next @app. decorator. It contains the marker comment.
marker = "class LoyaltyCreate(BaseModel)"
broken_signature = 'def add_loyalty(tenant_id,customer_id,payload:LoyaltyCreate'

if broken_signature not in text:
    print("SKIP: broken add_loyalty already fixed or never applied")
    sys.exit(0)

# Find the decorator immediately above the broken function
idx = text.find(broken_signature)
if idx < 0:
    print("SKIP: broken function not found")
    sys.exit(0)

# Walk backwards to the @app.post decorator that starts this block
start = text.rfind("@app.post", 0, idx)
if start < 0:
    print("ERROR: could not find decorator above broken function")
    sys.exit(1)

# Walk forwards to the next @app decorator
end = text.find("\n@app.", idx + 10)
if end < 0:
    end = len(text)

removed = text[start:end]
text = text[:start] + text[end:]

# Remove any stray reference to the class name in case the insertion was partial
text = text.replace("class LoyaltyCreate(BaseModel):\n    points:int; reason:str; reference_id:str|None=None\n", "")

# Clean up excessive blank lines left behind
text = re.sub(r"\n{4,}", "\n\n\n", text)

MAIN.write_text(text, encoding="utf-8")
print(f"Removed broken add_loyalty block ({len(removed)} chars)")
print(f"main.py now {len(text)} bytes")