"""Session 12 - Full QR architecture installer.

Replaces the existing POST /qr and GET /qr/{token} endpoints with the
blueprint-compliant set:

    POST   /api/v1/tenants/{tid}/qr
    GET    /api/v1/tenants/{tid}/qr
    GET    /api/v1/tenants/{tid}/qr/{id}
    GET    /api/v1/tenants/{tid}/qr/{id}/png
    DELETE /api/v1/tenants/{tid}/qr/{id}
    GET    /api/v1/tenants/{tid}/qr-analytics
    GET    /api/v1/public/qr/{token}/resolve
    POST   /api/v1/public/business/{slug}/qr-scan
    GET    /c/{token}                          (Next.js side handles this)

Also wires ensure_qr_schema() into startup.

Idempotent. Safe to rerun.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: app/main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION12_FULL_QR" in text:
    print("SKIP: Session 12 already applied")
    sys.exit(0)


NEW_ENDPOINTS = '''# ============ SESSION12_FULL_QR ============

class QrCreateRequest(BaseModel):
    kind: str = Field(default="business", pattern="^(business|context|campaign)$")
    label: str = Field(default="Business QR", max_length=160)
    context_type: str | None = Field(default=None, max_length=40)
    context_value: str | None = Field(default=None, max_length=120)
    campaign_id: str | None = Field(default=None, max_length=36)


@app.post("/api/v1/tenants/{tenant_id}/qr", status_code=201)
def create_qr_endpoint(tenant_id, payload: QrCreateRequest, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import create_qr
    from .security import audit
    try:
        entry = create_qr(
            db, tenant_id,
            kind=payload.kind, label=payload.label,
            context_type=payload.context_type, context_value=payload.context_value,
            campaign_id=payload.campaign_id, created_by=user.id,
            public_base=settings.public_app_url,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit(db, tenant_id=tenant_id, actor_id=user.id,
          action="qr.created", target_type="qr", target_id=entry["id"],
          detail={"kind": entry["kind"], "label": entry["label"]})
    return entry


@app.get("/api/v1/tenants/{tenant_id}/qr")
def list_qr_endpoint(tenant_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import list_qrs
    items = list_qrs(db, tenant_id)
    # attach full URL
    base = (settings.public_app_url or "").rstrip("/")
    for it in items:
        it["url"] = f"{base}/c/{it['token']}"
    return {"items": items}


@app.get("/api/v1/tenants/{tenant_id}/qr/{qr_id}")
def get_qr_endpoint(tenant_id, qr_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import get_qr
    entry = get_qr(db, tenant_id, qr_id)
    if not entry:
        raise HTTPException(404, "QR not found")
    base = (settings.public_app_url or "").rstrip("/")
    entry["url"] = f"{base}/c/{entry['token']}"
    return entry


@app.get("/api/v1/tenants/{tenant_id}/qr/{qr_id}/png")
def get_qr_png_endpoint(tenant_id, qr_id, size: int = 400, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import generate_qr_png_for_entry
    from fastapi.responses import Response
    try:
        png, url = generate_qr_png_for_entry(
            db, tenant_id, qr_id,
            size=min(max(int(size), 100), 1000),
            public_base=settings.public_app_url,
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@app.delete("/api/v1/tenants/{tenant_id}/qr/{qr_id}")
def delete_qr_endpoint(tenant_id, qr_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import delete_qr
    from .security import audit
    ok = delete_qr(db, tenant_id, qr_id)
    if not ok:
        raise HTTPException(404, "QR not found")
    audit(db, tenant_id=tenant_id, actor_id=user.id,
          action="qr.deleted", target_type="qr", target_id=qr_id)
    return {"deleted": True}


@app.get("/api/v1/tenants/{tenant_id}/qr-analytics")
def qr_analytics_endpoint(tenant_id, days: int = 30, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .qr import qr_analytics
    return qr_analytics(db, tenant_id, days=days)


@app.get("/api/v1/public/qr/{token}/resolve")
def public_qr_resolve(token: str, db: Session = Depends(get_db)):
    from .qr import resolve_token
    info = resolve_token(db, token)
    if not info:
        raise HTTPException(404, "QR not found or tenant inactive")
    return info


class QrScanRequest(BaseModel):
    token: str = Field(min_length=4, max_length=100)
    customer_id: str | None = Field(default=None, max_length=36)


@app.post("/api/v1/public/business/{slug}/qr-scan")
def public_qr_scan(slug: str, payload: QrScanRequest, request: Request, db: Session = Depends(get_db)):
    from .qr import resolve_token, record_scan
    t = db.scalar(select(Tenant).where(Tenant.slug == slug.lower()))
    if not t:
        raise HTTPException(404, "Business not found")
    info = resolve_token(db, payload.token)
    if not info or info["tenant_slug"] != t.slug:
        raise HTTPException(404, "QR not found")
    # capture metadata
    ua = request.headers.get("user-agent")
    ref = request.headers.get("referer") or request.headers.get("referrer")
    ip = request.client.host if request.client else None
    result = record_scan(
        db,
        tenant_id=t.id,
        qr_id=info["qr_id"],
        token=info["token"],
        kind=info["kind"],
        context_type=info["context_type"],
        context_value=info["context_value"],
        campaign_id=info["campaign_id"],
        customer_id=payload.customer_id,
        user_agent=ua, referrer=ref, ip=ip,
    )
    return {**result, "context_type": info["context_type"], "context_value": info["context_value"], "campaign_id": info["campaign_id"], "kind": info["kind"]}

# ============ END SESSION12 ============

'''

# Insert before the final feature-gates marker, or at the end.
marker = "# === ENDPOINT FEATURE GATES ==="
if marker in text:
    text = text.replace(marker, NEW_ENDPOINTS + marker, 1)
    print("  inserted session-12 endpoints before ENDPOINT FEATURE GATES marker")
else:
    text = text.rstrip() + "\n" + NEW_ENDPOINTS + "\n"
    print("  appended session-12 endpoints at end of file")

# Wire schema migration into startup()
if "ensure_qr_schema" not in text:
    startup_marker = "async def startup():\n    install_signal_handlers(app)\n    ensure_schema()"
    if startup_marker in text:
        text = text.replace(
            startup_marker,
            "async def startup():\n    install_signal_handlers(app)\n    ensure_schema()\n"
            "    try:\n"
            "        from .qr import ensure_qr_schema\n"
            "        from .db import engine as _engine\n"
            "        ensure_qr_schema(_engine)\n"
            "    except Exception:\n"
            "        pass",
            1,
        )
        print("  wired ensure_qr_schema into startup()")
    else:
        # try the older startup signature without signal handlers
        alt = "async def startup():\n    ensure_schema()"
        if alt in text:
            text = text.replace(
                alt,
                "async def startup():\n    ensure_schema()\n"
                "    try:\n"
                "        from .qr import ensure_qr_schema\n"
                "        from .db import engine as _engine\n"
                "        ensure_qr_schema(_engine)\n"
                "    except Exception:\n"
                "        pass",
                1,
            )
            print("  wired ensure_qr_schema into startup() (alt signature)")
        else:
            print("  WARNING: startup() not found; call ensure_qr_schema(engine) manually")

# Mark
if "SESSION12_FULL_QR" not in text:
    text = text.rstrip() + "\n\n# SESSION12_FULL_QR\n"

MAIN.write_text(text, encoding="utf-8")
print()
print(f"Session 12 install complete. main.py now {len(text)} bytes.")