"""Add platform_messages endpoints to main.py."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MAIN = HERE / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION17B_MESSAGES" in text:
    print("SKIP: message endpoints already present")
    sys.exit(0)

NEW = '''# ============ SESSION17B_MESSAGES ============

class PlatformMessageRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=300)
    body: str = Field(default="", max_length=8000)
    send_email: bool = True


@app.get("/api/v1/platform/messages")
def platform_messages_list(tenant_id: str = "", limit: int = 200, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_messages import list_messages
    return {"items": list_messages(db, tenant_id=tenant_id or None, limit=limit)}


@app.post("/api/v1/platform/tenants/{tenant_id}/messages", status_code=201)
def platform_message_send(tenant_id: str, payload: PlatformMessageRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_messages import send_message
    try:
        return send_message(db, tenant_id=tenant_id, subject=payload.subject, body=payload.body, from_admin_id=user.id, send_email=payload.send_email)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.patch("/api/v1/platform/messages/{message_id}/read")
def platform_message_read(message_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_messages import mark_read
    r = mark_read(db, message_id)
    if not r:
        raise HTTPException(404, "Message not found")
    return r

# ============ END SESSION17B_MESSAGES ============

'''

marker = "# === ENDPOINT FEATURE GATES ==="
if marker in text:
    text = text.replace(marker, NEW + marker, 1)
    print("  inserted message endpoints")
else:
    text = text.rstrip() + "\n" + NEW + "\n"
    print("  appended message endpoints")

if "SESSION17B_MESSAGES" not in text:
    text = text.rstrip() + "\n\n# SESSION17B_MESSAGES\n"

MAIN.write_text(text, encoding="utf-8")
print(f"main.py now {len(text)} bytes.")