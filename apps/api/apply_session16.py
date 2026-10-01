"""Session 16 - Production Hardening installer.

1.  Wires SecurityHeadersMiddleware + RequestSizeLimitMiddleware into main.py
2.  Replaces /health with the enriched version
3.  Adds auth_rate_limit() calls to /auth/login, /auth/register,
    /auth/password-reset/request
4.  Installs graceful-shutdown signal handlers in startup()

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

if "SESSION16_HARDENING" in text:
    print("SKIP: Session 16 already applied")
    sys.exit(0)


# ---------------------------------------------------------------------------
# 1. Add import
# ---------------------------------------------------------------------------

if "from .hardening import" not in text:
    anchor = "from .health import router as health_router\n"
    if anchor not in text:
        print("WARNING: health_router import anchor not found; inserting after middleware import")
        anchor = "from .middleware import RequestContextMiddleware\n"
    new_import = anchor + (
        "from .hardening import (\n"
        "    SecurityHeadersMiddleware, RequestSizeLimitMiddleware,\n"
        "    auth_rate_limit, enrich_health, install_signal_handlers,\n"
        ")\n"
    )
    if anchor in text:
        text = text.replace(anchor, new_import, 1)
        print("  added hardening import")
    else:
        print("WARNING: could not place hardening import; add manually")


# ---------------------------------------------------------------------------
# 2. Add middlewares right after CORS
# ---------------------------------------------------------------------------

if "SecurityHeadersMiddleware" in text and "app.add_middleware(SecurityHeadersMiddleware" not in text:
    cors_anchor = "    allow_headers=[\"*\"],\n)"
    if cors_anchor in text:
        text = text.replace(
            cors_anchor,
            cors_anchor + (
                "\napp.add_middleware(SecurityHeadersMiddleware)\n"
                "app.add_middleware(RequestSizeLimitMiddleware, max_bytes=2 * 1024 * 1024)\n"
            ),
            1,
        )
        print("  added SecurityHeaders + RequestSizeLimit middlewares")
    else:
        print("WARNING: CORS middleware block not found; add middlewares manually")


# ---------------------------------------------------------------------------
# 3. Replace /health with enriched version
# ---------------------------------------------------------------------------

old_health = '''@app.get("/health",response_model=Health)
def health(): return {"status":"ok","service":"ai-growth-os-api","commit":__import__("os").environ.get("RENDER_GIT_COMMIT","unknown")}'''

new_health = '''@app.get("/health")
def health():
    out = enrich_health()
    out["commit"] = __import__("os").environ.get("RENDER_GIT_COMMIT", "unknown")
    return out'''

if old_health in text:
    text = text.replace(old_health, new_health, 1)
    print("  replaced /health with enriched version")
elif '@app.get("/health")' in text and 'enrich_health' in text:
    print("  SKIP /health (already enriched)")
else:
    # Fallback: find the health route block
    m = re.search(r'@app\.get\("/health".*?\n(.*?)\n(?=@app\.)', text, re.DOTALL)
    if m:
        text = text[:m.start()] + new_health + "\n\n" + text[m.end():]
        print("  replaced /health via regex")
    else:
        print("  WARNING: /health route not found")


# ---------------------------------------------------------------------------
# 4. Add auth_rate_limit calls
# ---------------------------------------------------------------------------

def add_rate_limit(source: str, decorator_line: str) -> tuple:
    """Insert an await auth_rate_limit() call at the top of a route function."""
    idx = source.find(decorator_line)
    if idx < 0:
        return source, False
    # find "def <name>(" after decorator
    body_idx = source.find("):", idx)
    if body_idx < 0:
        return source, False
    body_idx = source.find("\n", body_idx) + 1
    # check it isn't already there
    snippet = source[body_idx:body_idx + 400]
    if "auth_rate_limit" in snippet:
        return source, True
    # infer payload variable — most auth routes take (payload)
    inject = (
        "    try:\n"
        "        await auth_rate_limit(request, getattr(payload, 'email', None))\n"
        "    except NameError:\n"
        "        await auth_rate_limit(request)\n"
    )
    return source[:body_idx] + inject + source[body_idx:], True


# Add Request param + call to /auth/login
if 'auth_rate_limit(request' not in text:
    # /auth/login
    old_login_sig = 'def login(payload:LoginRequest,db:Session=Depends(get_db)):'
    new_login_sig = (
        'async def login(request:Request,payload:LoginRequest,db:Session=Depends(get_db)):\n'
        '    await auth_rate_limit(request, payload.email)'
    )
    if old_login_sig in text:
        text = text.replace(old_login_sig, new_login_sig, 1)
        print("  added auth_rate_limit to /auth/login")

    # /auth/register
    old_reg_sig = 'def register(payload:RegisterRequest,db:Session=Depends(get_db)):'
    new_reg_sig = (
        'async def register(request:Request,payload:RegisterRequest,db:Session=Depends(get_db)):\n'
        '    await auth_rate_limit(request, payload.email)'
    )
    if old_reg_sig in text:
        text = text.replace(old_reg_sig, new_reg_sig, 1)
        print("  added auth_rate_limit to /auth/register")

    # /auth/password-reset/request
    old_pr_sig = 'async def password_reset_request(payload:PasswordResetRequest,db:Session=Depends(get_db)):'
    new_pr_sig = (
        'async def password_reset_request(request:Request,payload:PasswordResetRequest,db:Session=Depends(get_db)):\n'
        '    await auth_rate_limit(request, payload.email)'
    )
    if old_pr_sig in text:
        text = text.replace(old_pr_sig, new_pr_sig, 1)
        print("  added auth_rate_limit to /auth/password-reset/request")


# ---------------------------------------------------------------------------
# 5. Install signal handlers in startup
# ---------------------------------------------------------------------------

if "install_signal_handlers" not in text.split("SESSION16_HARDENING")[0]:
    startup_marker = "async def startup():\n    ensure_schema()"
    if startup_marker in text:
        text = text.replace(
            startup_marker,
            "async def startup():\n    install_signal_handlers(app)\n    ensure_schema()",
            1,
        )
        print("  installed graceful-shutdown signal handlers")


# ---------------------------------------------------------------------------
# 6. Mark the file
# ---------------------------------------------------------------------------

if "SESSION16_HARDENING" not in text:
    text = text.rstrip() + "\n\n# SESSION16_HARDENING\n"

MAIN.write_text(text, encoding="utf-8")
print()
print(f"Session 16 install complete. main.py now {len(text)} bytes.")