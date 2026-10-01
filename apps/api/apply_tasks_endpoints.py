"""Add /api/v1/platform/tasks endpoints to main.py."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MAIN = HERE / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: main.py not found")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION17B_TASKS" in text:
    print("SKIP: already present")
    sys.exit(0)

NEW = '''# ============ SESSION17B_TASKS ============

class TaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str = Field(default="", max_length=8000)
    due_at: str = Field(min_length=10, max_length=40)
    tenant_id: str | None = None
    kind: str = Field(default="followup", max_length=40)
    priority: str = Field(default="normal", max_length=20)


class TaskStatusRequest(BaseModel):
    status: str = Field(pattern="^(pending|done|cancelled)$")


@app.get("/api/v1/platform/tasks")
def platform_tasks_list(start: str = "", end: str = "", tenant_id: str = "", status: str = "", limit: int = 300, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tasks import list_tasks, overdue_count
    items = list_tasks(db, start_iso=start or None, end_iso=end or None, tenant_id=tenant_id or None, status=status or None, limit=limit)
    return {"items": items, "overdue": overdue_count(db)}


@app.post("/api/v1/platform/tasks", status_code=201)
def platform_tasks_create(payload: TaskCreateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tasks import create_task
    try:
        due = datetime.fromisoformat(payload.due_at.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(400, "due_at must be ISO format")
    try:
        return create_task(db, title=payload.title, due_at=due, notes=payload.notes, tenant_id=payload.tenant_id, kind=payload.kind, priority=payload.priority, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/platform/tasks/{task_id}/status")
def platform_tasks_set_status(task_id: str, payload: TaskStatusRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tasks import set_status
    try:
        return set_status(db, task_id, payload.status, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/v1/platform/tasks/{task_id}")
def platform_tasks_delete(task_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tasks import delete_task
    ok = delete_task(db, task_id)
    if not ok:
        raise HTTPException(404, "Task not found")
    return {"deleted": True}

# ============ END SESSION17B_TASKS ============

'''

marker = "# === ENDPOINT FEATURE GATES ==="
if marker in text:
    text = text.replace(marker, NEW + marker, 1)
    print("  inserted task endpoints")
else:
    text = text.rstrip() + "\n" + NEW + "\n"
    print("  appended task endpoints")

if "SESSION17B_TASKS" not in text:
    text = text.rstrip() + "\n\n# SESSION17B_TASKS\n"

MAIN.write_text(text, encoding="utf-8")
print(f"main.py now {len(text)} bytes.")