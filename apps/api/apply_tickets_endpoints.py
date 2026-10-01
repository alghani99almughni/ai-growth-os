"""Add ticket endpoints to main.py."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MAIN = HERE / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION17B_TICKETS" in text:
    print("SKIP: ticket endpoints already present")
    sys.exit(0)

NEW = '''# ============ SESSION17B_TICKETS ============

class TicketCreateRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=8000)
    category: str = Field(default="support", max_length=40)
    priority: str = Field(default="normal", max_length=20)


class TicketStatusRequest(BaseModel):
    status: str = Field(pattern="^(new|acknowledged|in_progress|waiting_on_tenant|resolved|closed)$")


class TicketReplyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    from_tenant: bool = False


class TicketAssignRequest(BaseModel):
    staff_user_id: str | None = None


@app.get("/api/v1/platform/tickets")
def platform_tickets_list(status: str = "", category: str = "", tenant_id: str = "", include_breached_only: bool = False, limit: int = 200, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import list_tickets, sla_summary
    items = list_tickets(db, tenant_id=tenant_id or None, status=status or None, category=category or None, include_breached_only=include_breached_only, limit=limit)
    return {"items": items, "summary": sla_summary(db, tenant_id=tenant_id or None)}


@app.get("/api/v1/platform/tickets/{ticket_id}")
def platform_ticket_get(ticket_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import get_ticket
    t = get_ticket(db, ticket_id)
    if not t:
        raise HTTPException(404, "Ticket not found")
    return t


@app.post("/api/v1/platform/tickets", status_code=201)
def platform_ticket_create(payload: TicketCreateRequest, tenant_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import create_ticket
    try:
        return create_ticket(db, tenant_id=tenant_id, subject=payload.subject, body=payload.body, category=payload.category, priority=payload.priority, created_by=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/platform/tickets/{ticket_id}/status")
def platform_ticket_set_status(ticket_id: str, payload: TicketStatusRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import set_status
    try:
        return set_status(db, ticket_id, payload.status, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/platform/tickets/{ticket_id}/assign")
def platform_ticket_assign(ticket_id: str, payload: TicketAssignRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import assign
    try:
        return assign(db, ticket_id, payload.staff_user_id, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/v1/platform/tickets/{ticket_id}/reply")
def platform_ticket_reply(ticket_id: str, payload: TicketReplyRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .tickets import reply
    try:
        return reply(db, ticket_id, payload.message, from_tenant=payload.from_tenant, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

# ============ END SESSION17B_TICKETS ============

'''

marker = "# === ENDPOINT FEATURE GATES ==="
if marker in text:
    text = text.replace(marker, NEW + marker, 1)
    print("  inserted ticket endpoints")
else:
    text = text.rstrip() + "\n" + NEW + "\n"
    print("  appended ticket endpoints")

if "SESSION17B_TICKETS" not in text:
    text = text.rstrip() + "\n\n# SESSION17B_TICKETS\n"

MAIN.write_text(text, encoding="utf-8")
print(f"main.py now {len(text)} bytes.")