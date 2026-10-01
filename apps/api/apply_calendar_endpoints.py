"""Add calendar endpoints to main.py."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MAIN = HERE / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION17B_CALENDAR" in text:
    print("SKIP: calendar endpoints already present")
    sys.exit(0)

NEW = '''# ============ SESSION17B_CALENDAR ============

@app.get("/api/v1/platform/calendar")
def platform_calendar(year: int = 0, month: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .calendar import month_view
    now = datetime.utcnow()
    y = year or now.year
    m = month or now.month
    try:
        return month_view(db, y, m)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/v1/platform/follow-ups")
def platform_follow_ups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .calendar import follow_ups
    return follow_ups(db)

# ============ END SESSION17B_CALENDAR ============

'''

marker = "# === ENDPOINT FEATURE GATES ==="
if marker in text:
    text = text.replace(marker, NEW + marker, 1)
    print("  inserted calendar endpoints")
else:
    text = text.rstrip() + "\n" + NEW + "\n"
    print("  appended calendar endpoints")

if "SESSION17B_CALENDAR" not in text:
    text = text.rstrip() + "\n\n# SESSION17B_CALENDAR\n"

MAIN.write_text(text, encoding="utf-8")
print(f"main.py now {len(text)} bytes.")