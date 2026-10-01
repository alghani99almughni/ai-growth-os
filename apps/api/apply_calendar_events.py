"""Add /platform/calendar/events endpoint to main.py."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MAIN = HERE / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: main.py not found")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION17B_CAL_EVENTS" in text:
    print("SKIP: already present")
    sys.exit(0)

NEW = '''# ============ SESSION17B_CAL_EVENTS ============

@app.get("/api/v1/platform/calendar/events")
def platform_calendar_events(start: str, end: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .calendar import events_between
    try:
        return {"items": events_between(db, start, end)}
    except ValueError as exc:
        raise HTTPException(400, str(exc))

# ============ END SESSION17B_CAL_EVENTS ============

'''

marker = "# === ENDPOINT FEATURE GATES ==="
if marker in text:
    text = text.replace(marker, NEW + marker, 1)
    print("  inserted calendar events endpoint")
else:
    text = text.rstrip() + "\n" + NEW + "\n"
    print("  appended calendar events endpoint")

if "SESSION17B_CAL_EVENTS" not in text:
    text = text.rstrip() + "\n\n# SESSION17B_CAL_EVENTS\n"

MAIN.write_text(text, encoding="utf-8")
print(f"main.py now {len(text)} bytes.")