"""Add ends_at to all events, and include tasks with duration."""
import pathlib
import sys
from datetime import timedelta

HERE = pathlib.Path(__file__).resolve().parent
CAL = HERE / "app" / "calendar.py"

if not CAL.exists():
    print("ERROR: app/calendar.py not found")
    sys.exit(1)

text = CAL.read_text(encoding="utf-8")

if "duration_minutes" in text:
    print("SKIP: already patched")
    sys.exit(0)

# Add a helper that computes ends_at from at + duration
helper = '''

def _with_ends(event: dict, default_minutes: int = 30) -> dict:
    """Add ends_at to an event dict based on at + duration_minutes."""
    from datetime import datetime as _dt
    try:
        start = _dt.fromisoformat(event["at"])
    except Exception:
        return event
    mins = int(event.get("duration_minutes") or default_minutes)
    event["ends_at"] = (start + timedelta(minutes=mins)).isoformat()
    event.setdefault("duration_minutes", mins)
    return event

'''

anchor = "def events_between(db: Session, start_iso: str, end_iso: str) -> list:"
if anchor not in text:
    print("ERROR: events_between not found")
    sys.exit(1)
text = text.replace(anchor, helper.lstrip() + "\n" + anchor, 1)

# Replace the task-append block with a duration-aware version
old_task_block = '''    try:
        from .models_growth import PlatformTask
        for task in db.scalars(select(PlatformTask).where(PlatformTask.due_at >= start, PlatformTask.due_at < end)).all():
            events.append({
                "at": task.due_at.isoformat(),
                "kind": "task",
                "title": ("✓ " if task.status == "done" else "") + task.title,
                "tenant_id": task.tenant_id,
                "link": "/platform/calendar",
                "meta": {"status": task.status, "priority": task.priority, "task_id": task.id},
            })
    except Exception:
        pass

    events.sort(key=lambda x: x["at"])
    return events'''

new_task_block = '''    try:
        from .models_growth import PlatformTask
        for task in db.scalars(select(PlatformTask).where(PlatformTask.due_at >= start, PlatformTask.due_at < end)).all():
            events.append({
                "at": task.due_at.isoformat(),
                "kind": "task",
                "title": ("✓ " if task.status == "done" else "") + task.title,
                "tenant_id": task.tenant_id,
                "link": "/platform/calendar",
                "duration_minutes": int(getattr(task, "duration_minutes", 30) or 30),
                "all_day": bool(getattr(task, "all_day", False)),
                "meta": {"status": task.status, "priority": task.priority, "task_id": task.id},
            })
    except Exception:
        pass

    events = [_with_ends(e) for e in events]
    events.sort(key=lambda x: x["at"])
    return events'''

if old_task_block not in text:
    print("ERROR: task block not found")
    sys.exit(1)
text = text.replace(old_task_block, new_task_block, 1)

CAL.write_text(text, encoding="utf-8")
print("calendar.py updated with ends_at + duration")