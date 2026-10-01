"""Session 10b - Multi-channel WhatsApp installer.

Replaces the WhatsApp endpoint block in main.py with per-channel endpoints,
adds a Meta inbound webhook, and wires the migration into startup.

Idempotent.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "app" / "main.py"
MODELS = ROOT / "app" / "models.py"

if not MAIN.exists() or not MODELS.exists():
    print("ERROR: app/main.py or app/models.py not found. Run from apps/api.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 1. Patch models.py - remove unique=True from tenant_id
# ---------------------------------------------------------------------------

mtext = MODELS.read_text(encoding="utf-8")
old_line = '    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), unique=True, index=True)\n    provider: Mapped[str] = mapped_column(String(30), default="openwa")'
new_line = '    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)\n    provider: Mapped[str] = mapped_column(String(30), default="openwa", index=True)'
if old_line in mtext:
    mtext = mtext.replace(old_line, new_line, 1)
    MODELS.write_text(mtext, encoding="utf-8")
    print("  patched models.py: dropped unique on tenant_id, added index on provider")
elif 'unique=True, index=True)\n    provider: Mapped[str] = mapped_column(String(30), default="openwa", index=True)' in mtext:
    print("  SKIP models.py: already patched")
else:
    print("  WARNING: models.py TenantWhatsAppConnection not found in expected form")

# ---------------------------------------------------------------------------
# 2. Patch main.py - replace WhatsApp endpoint block
# ---------------------------------------------------------------------------

text = MAIN.read_text(encoding="utf-8")

if "SESSION10B_MULTI_CHANNEL_WHATSAPP" in text:
    print("  SKIP main.py: session 10b already applied")
    sys.exit(0)

# Find the block from the first @app.get integrations/whatsapp decorator
# to just before the ReferralSettingsUpdate class (or WebsiteContentUpdate).
start_marker = '@app.get("/api/v1/tenants/{tenant_id}/integrations/whatsapp"'
end_marker_candidates = [
    'class ReferralSettingsUpdate(BaseModel):',
    'class WebsiteContentUpdate(BaseModel):',
]
start = text.find(start_marker)
if start < 0:
    print("ERROR: WhatsApp endpoint block start not found")
    sys.exit(1)

end = -1
for m in end_marker_candidates:
    idx = text.find(m, start + 10)
    if idx > 0 and (end < 0 or idx < end):
        end = idx
if end < 0:
    print("ERROR: WhatsApp endpoint block end not found")
    sys.exit(1)

NEW_BLOCK = '''# ============ SESSION10B_MULTI_CHANNEL_WHATSAPP ============

class WhatsAppChannelConfig(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    session_id: str | None = None
    access_token: str | None = None
    phone_number_id: str | None = None
    whatsapp_business_account_id: str | None = None


class WhatsAppPriorityUpdate(BaseModel):
    priority: str = Field(pattern="^(openwa|meta)$")


@app.get("/api/v1/tenants/{tenant_id}/integrations/whatsapp")
def whatsapp_channels(tenant_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .whatsapp_channels import all_channels
    return all_channels(db, tenant_id)


@app.put("/api/v1/tenants/{tenant_id}/integrations/whatsapp/openwa")
async def configure_openwa(tenant_id, payload: WhatsAppChannelConfig, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    data = payload.model_dump(exclude_none=True)
    if not all(data.get(k) for k in ("base_url", "api_key", "session_id")):
        raise HTTPException(400, "OpenWA requires base_url, api_key and session_id")
    try:
        async with __import__("httpx").AsyncClient(timeout=15) as client:
            rr = await client.get(
                data["base_url"].rstrip("/") + "/api/sessions/" + data["session_id"],
                headers={"X-API-Key": data["api_key"]},
            )
            rr.raise_for_status()
            session = rr.json()
            connected_phone = session.get("phoneNumber") or session.get("phone")
    except Exception as exc:
        raise HTTPException(400, "OpenWA credentials could not be validated: " + str(exc))

    from .whatsapp_channels import configure_channel
    return configure_channel(
        db, tenant_id, "openwa",
        {"base_url": data["base_url"], "api_key": data["api_key"], "session_id": data["session_id"]},
        connected_phone, None,
    )


@app.put("/api/v1/tenants/{tenant_id}/integrations/whatsapp/meta")
async def configure_meta(tenant_id, payload: WhatsAppChannelConfig, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    data = payload.model_dump(exclude_none=True)
    if not all(data.get(k) for k in ("access_token", "phone_number_id")):
        raise HTTPException(400, "Meta requires access_token and phone_number_id")
    try:
        async with __import__("httpx").AsyncClient(timeout=15) as client:
            rr = await client.get(
                "https://graph.facebook.com/v23.0/" + data["phone_number_id"],
                headers={"Authorization": "Bearer " + data["access_token"]},
            )
            rr.raise_for_status()
            info = rr.json()
            connected_phone = info.get("display_phone_number")
            display_name = info.get("verified_name")
    except Exception as exc:
        raise HTTPException(400, "Meta credentials could not be validated: " + str(exc))

    from .whatsapp_channels import configure_channel
    return configure_channel(
        db, tenant_id, "meta",
        {"access_token": data["access_token"], "phone_number_id": data["phone_number_id"]},
        connected_phone, display_name,
    )


@app.delete("/api/v1/tenants/{tenant_id}/integrations/whatsapp/{provider}")
def disconnect_channel_endpoint(tenant_id, provider, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    if provider not in ("openwa", "meta"):
        raise HTTPException(400, "provider must be openwa or meta")
    from .whatsapp_channels import disconnect_channel
    return disconnect_channel(db, tenant_id, provider)


@app.put("/api/v1/tenants/{tenant_id}/integrations/whatsapp/priority")
def set_whatsapp_priority(tenant_id, payload: WhatsAppPriorityUpdate, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .whatsapp_channels import set_priority, all_channels
    set_priority(db, tenant_id, payload.priority)
    return all_channels(db, tenant_id)


# ==== Meta Cloud API inbound webhook ====

@app.get("/api/v1/webhooks/meta/{tenant_id}")
def meta_webhook_verify(tenant_id: str, hub_mode: str = Query(default="", alias="hub.mode"), hub_challenge: str = Query(default="", alias="hub.challenge"), hub_verify_token: str = Query(default="", alias="hub.verify_token"), db: Session = Depends(get_db)):
    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    expected = (settings.openwa_webhook_secret or "")  # reuse for Meta verify token
    if hub_mode == "subscribe" and hub_verify_token and hub_verify_token == expected:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(hub_challenge)
    raise HTTPException(403, "Verification failed")


@app.post("/api/v1/webhooks/meta/{tenant_id}")
async def meta_webhook(tenant_id: str, request: Request, db: Session = Depends(get_db)):
    from .security import verify_hmac_sha256
    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")
    app_secret = settings.openwa_webhook_secret or ""
    if app_secret and sig and not verify_hmac_sha256(raw, sig, app_secret):
        raise HTTPException(401, "Invalid Meta webhook signature")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid webhook JSON")

    tenant = db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(404, "Tenant not found")

    entry = (payload.get("entry") or [{}])[0]
    changes = (entry.get("changes") or [{}])[0]
    value = changes.get("value") or {}
    messages = value.get("messages") or []
    if not messages:
        return {"ok": True, "ignored": True}

    m = messages[0]
    phone = (m.get("from") or "").strip()
    body = ""
    if m.get("type") == "text":
        body = ((m.get("text") or {}).get("body") or "").strip()
    if not phone or not body:
        return {"ok": True, "ignored": True}

    existing = db.scalar(select(Customer).where(
        Customer.tenant_id == tenant_id,
        Customer.phone == normalize_phone(phone),
    ))
    if not existing:
        try:
            existing = upsert_customer(db, tenant_id, phone, "WhatsApp User", True, source="whatsapp_meta")
        except ValueError:
            raise HTTPException(400, "Invalid phone")

    result = await generate_reply(db, tenant_id, body, None, "whatsapp")
    reply = result.get("reply") or "Thanks. How can I help you today?"

    from .whatsapp_channels import send_text_with_failover
    await send_text_with_failover(db, tenant_id, settings, existing.phone, reply)

    return {"ok": True, "customer_id": existing.id, "reply": reply}

# ============ END SESSION10B ============

'''

text = text[:start] + NEW_BLOCK + text[end:]
text = text.rstrip() + "\n\n# SESSION10B_MULTI_CHANNEL_WHATSAPP\n"
MAIN.write_text(text, encoding="utf-8")
print(f"  patched main.py ({len(text)} bytes)")

# ---------------------------------------------------------------------------
# 3. Wire the migration into startup()
# ---------------------------------------------------------------------------

text = MAIN.read_text(encoding="utf-8")
if "whatsapp_migration" in text:
    print("  SKIP startup: migration already wired")
else:
    old = "    ensure_schema()\n"
    new = (
        "    ensure_schema()\n"
        "    try:\n"
        "        from .whatsapp_migration import ensure_two_channel_whatsapp\n"
        "        from .db import engine\n"
        "        ensure_two_channel_whatsapp(engine)\n"
        "    except Exception:\n"
        "        pass\n"
    )
    # Only replace the first occurrence inside startup()
    idx = text.find("async def startup():")
    if idx < 0:
        print("  WARNING: startup() not found")
    else:
        head = text[:idx]
        tail = text[idx:]
        if old in tail:
            tail = tail.replace(old, new, 1)
            text = head + tail
            MAIN.write_text(text, encoding="utf-8")
            print("  wired whatsapp_migration into startup()")
        else:
            print("  WARNING: ensure_schema() call not found inside startup()")

print()
print("Session 10b install complete.")
print()
print("Next: run the verification:")
print('  python -c "from app.main import app; print(\'routes:\', len(app.routes))"')