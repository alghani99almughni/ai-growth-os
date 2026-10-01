"""Session 14 — TURN server integration installer.

Replaces the two static-ICE endpoints in main.py with ephemeral credential
endpoints that call app/turn.py. Idempotent.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
MAIN = ROOT / "app" / "main.py"

if not MAIN.exists():
    print("ERROR: app/main.py not found. Run from apps/api.")
    sys.exit(1)

text = MAIN.read_text(encoding="utf-8")

if "SESSION14_EPHEMERAL_TURN" in text:
    print("SKIP: Session 14 already applied")
    sys.exit(0)


def replace_function(src, decorator, new_body):
    start = src.find(decorator)
    if start < 0:
        return src, False
    end = src.find("\n@app.", start + 10)
    if end < 0:
        end = len(src)
    return src[:start] + new_body + src[end:], True


# ---------------------------------------------------------------------------
# 1. Staff ICE endpoint (authenticated)
# ---------------------------------------------------------------------------

NEW_STAFF_ICE = '''@app.get("/api/v1/tenants/{tenant_id}/voice/ice")
async def voice_ice_config(tenant_id, user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_tenant(user, tenant_id)
    from .turn import generate_ice_config
    result = await generate_ice_config(tenant_id=tenant_id, user_id=user.id)
    return {
        "ice_servers": result.ice_servers,
        "provider": result.provider,
        "ttl_seconds": result.ttl_seconds,
    }
'''

text, ok = replace_function(
    text,
    '@app.get("/api/v1/tenants/{tenant_id}/voice/ice")',
    NEW_STAFF_ICE,
)
print("  patched staff voice/ice" if ok else "  WARNING: staff voice/ice not found")


# ---------------------------------------------------------------------------
# 2. Public customer ICE endpoint
# ---------------------------------------------------------------------------

NEW_PUBLIC_ICE = '''@app.get("/api/v1/public/business/{slug}/voice/ice")
async def public_voice_ice(slug: str, db: Session = Depends(get_db)):
    t = db.scalar(select(Tenant).where(Tenant.slug == slug.lower()))
    if not t:
        raise HTTPException(404, "Business not found")
    if not _feature_config(db, t.id).get("ai_voice", True):
        raise HTTPException(403, "Voice calling is not available for this business")
    from .turn import generate_ice_config
    result = await generate_ice_config(tenant_id=t.id)
    return {
        "ice_servers": result.ice_servers,
        "provider": result.provider,
        "ttl_seconds": result.ttl_seconds,
    }
'''

text, ok = replace_function(
    text,
    '@app.get("/api/v1/public/business/{slug}/voice/ice")',
    NEW_PUBLIC_ICE,
)
print("  patched public voice/ice" if ok else "  WARNING: public voice/ice not found")


# ---------------------------------------------------------------------------
# 3. Health check for TURN config
# ---------------------------------------------------------------------------

if "turn_config_status" not in text:
    NEW_HEALTH = '''

@app.get("/api/v1/health/turn")
def turn_health(user=Depends(get_current_user)):
    from .turn import turn_config_status
    return turn_config_status()

# SESSION14_EPHEMERAL_TURN
'''
    text = text.rstrip() + NEW_HEALTH
    print("  added /api/v1/health/turn diagnostics endpoint")

MAIN.write_text(text, encoding="utf-8")
print()
print(f"Session 14 install complete. main.py now {len(text)} bytes.")