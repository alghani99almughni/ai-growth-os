"""Update tasks.py to support duration + all_day."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MOD = HERE / "app" / "tasks.py"

if not MOD.exists():
    print("ERROR: app/tasks.py not found")
    sys.exit(1)

text = MOD.read_text(encoding="utf-8")

if "duration_minutes" in text:
    print("SKIP: already updated")
    sys.exit(0)

# 1. Extend create_task signature
old_sig = '''def create_task(
    db: Session,
    *,
    title: str,
    due_at: datetime,
    notes: str = "",
    tenant_id: str | None = None,
    kind: str = "followup",
    priority: str = "normal",
    created_by: str | None = None,
) -> dict:'''
new_sig = '''def create_task(
    db: Session,
    *,
    title: str,
    due_at: datetime,
    notes: str = "",
    tenant_id: str | None = None,
    kind: str = "followup",
    priority: str = "normal",
    created_by: str | None = None,
    duration_minutes: int = 30,
    all_day: bool = False,
) -> dict:'''
if old_sig not in text:
    print("ERROR: create_task signature not found")
    sys.exit(1)
text = text.replace(old_sig, new_sig, 1)

# 2. Add fields to PlatformTask() construction
old_create = '''        created_by=created_by,
        created_at=datetime.utcnow(),
    )'''
new_create = '''        created_by=created_by,
        created_at=datetime.utcnow(),
        duration_minutes=max(5, int(duration_minutes or 30)),
        all_day=bool(all_day),
    )'''
if old_create not in text:
    print("ERROR: create body not found")
    sys.exit(1)
text = text.replace(old_create, new_create, 1)

# 3. Extend serializer
old_out = '''        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }'''
new_out = '''        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "duration_minutes": int(getattr(t, "duration_minutes", 30) or 30),
        "all_day": bool(getattr(t, "all_day", False)),
    }'''
if old_out not in text:
    print("ERROR: serializer not found")
    sys.exit(1)
text = text.replace(old_out, new_out, 1)

MOD.write_text(text, encoding="utf-8")
print("tasks.py updated with duration + all_day")