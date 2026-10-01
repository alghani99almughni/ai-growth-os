"""Add tenant-scoped calendar endpoints to main.py.

Same shape as /platform/calendar but scoped to the authenticated user's
own tenant. Tenants cannot see other tenants' data.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MAIN = HERE / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION17B_TENANT_CALENDAR" in text:
    print("SKIP: already present")
    sys.exit(0)

NEW = '''# ============ SESSION17B_TENANT_CALENDAR ============

class TenantTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=8000)
    due_at: str = Field(min_length=10, max_length=40)
    kind: str = Field(default="followup", max_length=40)
    priority: str = Field(default="normal", max_length=20)
    duration_minutes: int = Field(default=30, ge=5, le=1440)
    all_day: bool = False


def _require_tenant_self(user, tenant_id):
    """A tenant user can only access their own tenant. SuperAdmin can access any."""
    if user.role in ("platform_admin", "super_admin"):
        return
    if user.tenant_id != tenant_id:
        raise HTTPException(403, "Access denied")


@app.get("/api/v1/tenants/{tenant_id}/calendar")
def tenant_calendar_month(tenant_id, year: int = 0, month: int = 0, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .calendar import month_view
    from datetime import datetime as _dt
    now = _dt.utcnow()
    y = year or now.year
    m = month or now.month
    try:
        data = month_view(db, y, m)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # Filter signups to this tenant only
    for day in data["days"]:
        day["signups"] = [s for s in day["signups"] if s["id"] == tenant_id]
    return data


@app.get("/api/v1/tenants/{tenant_id}/calendar/events")
def tenant_calendar_events(tenant_id, start: str, end: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .calendar import events_between
    from .models_growth import PlatformTask
    from sqlalchemy import select as _select
    try:
        events = events_between(db, start, end)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # Only this tenant's events
    events = [e for e in events if e.get("tenant_id") == tenant_id]
    # Add this tenant's tasks
    try:
        from datetime import datetime as _dt
        start_dt = _dt.fromisoformat(start)
        end_dt = _dt.fromisoformat(end)
        task_rows = db.scalars(
            _select(PlatformTask).where(
                PlatformTask.tenant_id == tenant_id,
                PlatformTask.due_at >= start_dt,
                PlatformTask.due_at < end_dt,
            )
        ).all()
        for t in task_rows:
            dur = int(getattr(t, "duration_minutes", 30) or 30)
            at = t.due_at.isoformat()
            ends_at = (t.due_at + __import__("datetime").timedelta(minutes=dur)).isoformat()
            events.append({
                "at": at,
                "ends_at": ends_at,
                "kind": "task",
                "title": ("✓ " if t.status == "done" else "") + t.title,
                "tenant_id": tenant_id,
                "link": "/dashboard/calendar",
                "duration_minutes": dur,
                "all_day": bool(getattr(t, "all_day", False)),
                "meta": {"status": t.status, "priority": t.priority, "task_id": t.id},
            })
    except Exception:
        pass
    events.sort(key=lambda x: x.get("at", ""))
    return {"items": events}


@app.get("/api/v1/tenants/{tenant_id}/calendar/tasks")
def tenant_calendar_tasks(tenant_id, start: str = "", end: str = "", status: str = "", limit: int = 300, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .tasks import list_tasks
    items = list_tasks(db, start_iso=start or None, end_iso=end or None, tenant_id=tenant_id, status=status or None, limit=limit)
    return {"items": items}


@app.post("/api/v1/tenants/{tenant_id}/calendar/tasks", status_code=201)
def tenant_calendar_create_task(tenant_id, payload: TenantTaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .tasks import create_task
    from datetime import datetime as _dt
    try:
        due = _dt.fromisoformat(payload.due_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, "due_at must be ISO format")
    try:
        return create_task(
            db,
            title=payload.title,
            due_at=due,
            notes=payload.notes,
            tenant_id=tenant_id,
            kind=payload.kind,
            priority=payload.priority,
            created_by=user.id,
            duration_minutes=payload.duration_minutes,
            all_day=payload.all_day,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/tenants/{tenant_id}/calendar/tasks/{task_id}/status")
def tenant_calendar_set_task_status(tenant_id, task_id, payload: TaskStatusRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .tasks import set_status
    from .models_growth import PlatformTask
    t = db.get(PlatformTask, task_id)
    if not t or t.tenant_id != tenant_id:
        raise HTTPException(404, "Task not found")
    try:
        return set_status(db, task_id, payload.status, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/v1/tenants/{tenant_id}/calendar/tasks/{task_id}")
def tenant_calendar_delete_task(tenant_id, task_id, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    _require_tenant_self(user, tenant_id)
    from .models_growth import PlatformTask
    t = db.get(PlatformTask, task_id)
    if not t or t.tenant_id != tenant_id:
        raise HTTPException(404, "Task not found")
    db.delete(t)
    db.commit()
    return {"deleted": True}

# ============ END SESSION17B_TENANT_CALENDAR ============

'''

marker = "# === ENDPOINT FEATURE GATES ==="
if marker in text:
    text = text.replace(marker, NEW + marker, 1)
    print("  inserted tenant calendar endpoints")
else:
    text = text.rstrip() + "\n" + NEW + "\n"
    print("  appended tenant calendar endpoints")

if "SESSION17B_TENANT_CALENDAR" not in text:
    text = text.rstrip() + "\n\n# SESSION17B_TENANT_CALENDAR\n"

MAIN.write_text(text, encoding="utf-8")
print(f"main.py now {len(text)} bytes.")