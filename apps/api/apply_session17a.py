"""Session 17a - wire platform_settings + platform_tools into main.py.

Adds 11 endpoints under /api/v1/platform/:
    GET  /overview
    GET  /tenants
    GET  /tenants/{id}/detail
    GET  /tenants/{id}/overrides
    PUT  /tenants/{id}/overrides
    GET  /tenants/{id}/whatsapp
    GET  /tenants/{id}/razorpay
    GET  /tenants/{id}/activity
    POST /tenants/{id}/qr
    GET  /settings
    PUT  /settings

Also calls mark_tenant_seen() on every successful /auth/login.

Idempotent. Safe to rerun.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: app/main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION17A_PLATFORM_TOOLS" in text:
    print("SKIP: Session 17a already applied")
    sys.exit(0)


NEW_ENDPOINTS = '''# ============ SESSION17A_PLATFORM_TOOLS ============

class FeatureOverrideRequest(BaseModel):
    features: dict


class AdminQrRequest(BaseModel):
    kind: str = Field(default="business", pattern="^(business|context|campaign)$")
    label: str = Field(default="Admin generated QR", max_length=160)
    context_type: str | None = Field(default=None, max_length=40)
    context_value: str | None = Field(default=None, max_length=120)
    campaign_id: str | None = Field(default=None, max_length=36)


class PlatformSettingsUpdate(BaseModel):
    updates: dict


@app.get("/api/v1/platform/overview")
def platform_overview(days: int = 30, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import overview
    return overview(db, days=days)


@app.get("/api/v1/platform/tenants")
def platform_tenants_v2(search: str = "", status: str = "", limit: int = 500,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import list_tenants
    return {"items": list_tenants(db, search=search, status=status, limit=limit)}


@app.get("/api/v1/platform/tenants/{tenant_id}/detail")
def platform_tenant_detail(tenant_id: str,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(404, "Tenant not found")
    from .platform_tools import tenant_health_score, activity_metrics
    from .platform_settings import status as settings_status
    score = tenant_health_score(db, tenant_id)
    return {
        "id": t.id,
        "name": t.name,
        "slug": t.slug,
        "industry": t.industry,
        "status": t.status,
        "plan": getattr(t, "plan", None),
        "city": getattr(t, "city", None),
        "phone": getattr(t, "phone", None),
        "whatsapp_number": getattr(t, "whatsapp_number", None),
        "email": getattr(t, "email", None),
        "address": getattr(t, "address", None),
        "timezone": getattr(t, "timezone", None),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "last_seen_at": getattr(t, "last_seen_at", None).isoformat() if getattr(t, "last_seen_at", None) else None,
        "health_status": getattr(t, "health_status", "unknown"),
        "region": getattr(t, "region", "GLOBAL"),
        "compliance_flags": getattr(t, "compliance_flags", "{}"),
        "health_score": score,
        "activity": activity_metrics(db, tenant_id, days=30),
    }


@app.get("/api/v1/platform/tenants/{tenant_id}/overrides")
def platform_get_overrides(tenant_id: str,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import get_overrides
    return {"features": get_overrides(db, tenant_id)}


@app.put("/api/v1/platform/tenants/{tenant_id}/overrides")
def platform_set_overrides(tenant_id: str, payload: FeatureOverrideRequest,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import set_overrides
    return {"features": set_overrides(db, tenant_id, payload.features, actor_id=user.id)}


@app.get("/api/v1/platform/tenants/{tenant_id}/whatsapp")
def platform_whatsapp_status(tenant_id: str,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import whatsapp_status
    return whatsapp_status(db, tenant_id)


@app.get("/api/v1/platform/tenants/{tenant_id}/razorpay")
def platform_razorpay_status(tenant_id: str,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import razorpay_status
    return razorpay_status(db, tenant_id)


@app.get("/api/v1/platform/tenants/{tenant_id}/activity")
def platform_activity(tenant_id: str, days: int = 30,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import activity_metrics
    return activity_metrics(db, tenant_id, days=days)


@app.post("/api/v1/platform/tenants/{tenant_id}/qr", status_code=201)
def platform_admin_create_qr(tenant_id: str, payload: AdminQrRequest,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_tools import admin_create_qr
    try:
        return admin_create_qr(
            db, tenant_id,
            kind=payload.kind, label=payload.label,
            context_type=payload.context_type,
            context_value=payload.context_value,
            campaign_id=payload.campaign_id,
            admin_id=user.id,
            public_base=settings.public_app_url,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/v1/platform/settings")
def platform_get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_settings import get_all
    return get_all(db)


@app.put("/api/v1/platform/settings")
def platform_update_settings(payload: PlatformSettingsUpdate,
                              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_platform_admin(user)
    from .platform_settings import set_many
    return set_many(db, payload.updates, actor_id=user.id)

# ============ END SESSION17A ============

'''

# Insert before the final feature-gates marker, or at end
marker = "# === ENDPOINT FEATURE GATES ==="
if marker in text:
    text = text.replace(marker, NEW_ENDPOINTS + marker, 1)
    print("  inserted 11 platform endpoints before ENDPOINT FEATURE GATES marker")
else:
    text = text.rstrip() + "\n" + NEW_ENDPOINTS + "\n"
    print("  appended 11 platform endpoints at end of file")


# Add mark_tenant_seen call to /auth/login
if "mark_tenant_seen" not in text:
    old = '    return {"access_token":create_access_token(u),"token_type":"bearer","user":user_out(u),"tenant":t}'
    new = '''    try:
        from .platform_tools import mark_tenant_seen
        mark_tenant_seen(db, u.tenant_id)
    except Exception:
        pass
    return {"access_token":create_access_token(u),"token_type":"bearer","user":user_out(u),"tenant":t}'''
    # Only replace inside the login function — find the login function body
    login_idx = text.find("def login(request:Request,payload:LoginRequest")
    if login_idx < 0:
        login_idx = text.find("def login(payload:LoginRequest")
    if login_idx > 0:
        # Find the next occurrence of the old return line after login_idx
        ret_idx = text.find(old, login_idx)
        if ret_idx > 0 and ret_idx < login_idx + 2000:
            text = text[:ret_idx] + new + text[ret_idx + len(old):]
            print("  added mark_tenant_seen() to /auth/login")
        else:
            print("  WARNING: could not find login return line")
    else:
        print("  WARNING: could not find /auth/login function")


if "SESSION17A_PLATFORM_TOOLS" not in text:
    text = text.rstrip() + "\n\n# SESSION17A_PLATFORM_TOOLS\n"

MAIN.write_text(text, encoding="utf-8")
print()
print(f"Session 17a install complete. main.py now {len(text)} bytes.")