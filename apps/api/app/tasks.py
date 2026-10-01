"""Platform follow-up tasks."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def create_task(
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
) -> dict:
    from .models_growth import PlatformTask
    title = (title or "").strip()[:300]
    if not title:
        raise ValueError("title is required")
    task = PlatformTask(
        id=str(uuid.uuid4()),
        title=title,
        notes=(notes or "")[:8000],
        due_at=due_at,
        tenant_id=tenant_id,
        kind=kind,
        priority=priority,
        status="pending",
        created_by=created_by,
        created_at=datetime.utcnow(),
        duration_minutes=max(5, int(duration_minutes or 30)),
        all_day=bool(all_day),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    try:
        from .security import audit
        audit(db, tenant_id=tenant_id, actor_id=created_by, action="task.created", target_type="task", target_id=task.id, detail={"title": title, "due_at": due_at.isoformat()})
    except Exception:
        pass
    return _out(task)


def list_tasks(db: Session, *, start_iso: str | None = None, end_iso: str | None = None, tenant_id: str | None = None, status: str | None = None, limit: int = 300) -> list:
    from .models_growth import PlatformTask
    q = select(PlatformTask)
    if start_iso:
        try: q = q.where(PlatformTask.due_at >= datetime.fromisoformat(start_iso))
        except Exception: pass
    if end_iso:
        try: q = q.where(PlatformTask.due_at < datetime.fromisoformat(end_iso))
        except Exception: pass
    if tenant_id: q = q.where(PlatformTask.tenant_id == tenant_id)
    if status: q = q.where(PlatformTask.status == status)
    rows = db.scalars(q.order_by(PlatformTask.due_at).limit(min(max(limit, 1), 1000))).all()
    return [_out(r) for r in rows]


def set_status(db: Session, task_id: str, status: str, actor_id: str | None = None) -> dict:
    from .models_growth import PlatformTask
    if status not in ("pending", "done", "cancelled"):
        raise ValueError("status must be pending / done / cancelled")
    t = db.get(PlatformTask, task_id)
    if not t:
        raise ValueError("task not found")
    t.status = status
    t.completed_at = datetime.utcnow() if status == "done" else None
    db.commit()
    db.refresh(t)
    return _out(t)


def delete_task(db: Session, task_id: str) -> bool:
    from .models_growth import PlatformTask
    t = db.get(PlatformTask, task_id)
    if not t:
        return False
    db.delete(t)
    db.commit()
    return True


def overdue_count(db: Session) -> int:
    from .models_growth import PlatformTask
    try:
        return int(db.scalar(select(func.count(PlatformTask.id)).where(PlatformTask.status == "pending", PlatformTask.due_at < datetime.utcnow())) or 0)
    except Exception:
        return 0


def _out(t) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "notes": t.notes or "",
        "due_at": t.due_at.isoformat() if t.due_at else None,
        "tenant_id": t.tenant_id,
        "kind": t.kind,
        "priority": t.priority,
        "status": t.status,
        "created_by": t.created_by,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "duration_minutes": int(getattr(t, "duration_minutes", 30) or 30),
        "all_day": bool(getattr(t, "all_day", False)),
    }