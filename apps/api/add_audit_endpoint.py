"""Add GET /api/v1/platform/audit-log endpoint to main.py."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: app/main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION15_AUDIT_ENDPOINT" in text:
    print("SKIP: audit endpoint already added")
    sys.exit(0)

NEW = '''

# ============ SESSION15_AUDIT_ENDPOINT ============

@app.get("/api/v1/platform/audit-log")
def platform_audit_log(
    limit: int = 100,
    tenant_id: str | None = None,
    action: str | None = None,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_platform_admin(user)
    from .models_growth import AuditLog
    q = select(AuditLog).order_by(AuditLog.created_at.desc())
    if tenant_id:
        q = q.where(AuditLog.tenant_id == tenant_id)
    if action:
        q = q.where(AuditLog.action == action)
    rows = db.scalars(q.limit(min(max(limit, 1), 500))).all()
    return {"items": [{
        "id": r.id,
        "tenant_id": r.tenant_id,
        "actor_id": r.actor_id,
        "action": r.action,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "detail": json.loads(r.detail_json or "{}"),
        "request_id": r.request_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}

# ============ END SESSION15 ============
'''

text = text.rstrip() + NEW
MAIN.write_text(text, encoding="utf-8")
print(f"Audit endpoint added. main.py now {len(text)} bytes.")