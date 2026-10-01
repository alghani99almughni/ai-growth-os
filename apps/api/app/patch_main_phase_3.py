"""Mount Phase 3 routers in main.py.

Adds:
    - routes_offline.py   (/api/v1/voice/*)
    - routes_calls.py     (/api/v1/calls/*)

Both use the .include_router pattern. The patcher is idempotent - safe to
run multiple times.
"""

import pathlib

path = pathlib.Path("main.py")
text = path.read_text(encoding="utf-8")

if "routes_offline" in text and "routes_calls" in text:
    print("SKIP: already patched")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# 1. Add the imports after the last existing ".from .*" import line.
# ---------------------------------------------------------------------------

# Anchor at the last "from ." import. We assume there are no more imports
# after this block; if there are, they'll still work because .include_router
# comes later.
import_anchor = "from .tenant_policy import tenant_policy, capability_enabled, policy_context\n"

new_imports = (
    "from .tenant_policy import tenant_policy, capability_enabled, policy_context\n"
    "from .routes_offline import router as offline_router\n"
    "from .routes_calls import router as calls_router\n"
)

if "routes_offline" not in text:
    if import_anchor not in text:
        print("ERROR: import anchor not found")
        raise SystemExit(1)
    text = text.replace(import_anchor, new_imports, 1)
    print("Inserted: offline + calls imports")

# ---------------------------------------------------------------------------
# 2. Mount the routers right after the health router.
# ---------------------------------------------------------------------------

mount_anchor = "app.include_router(health_router)\n"

new_mounts = (
    "app.include_router(health_router)\n"
    "app.include_router(offline_router)\n"
    "app.include_router(calls_router)\n"
)

if "include_router(offline_router)" not in text:
    if mount_anchor not in text:
        print("ERROR: mount anchor not found")
        raise SystemExit(1)
    text = text.replace(mount_anchor, new_mounts, 1)
    print("Inserted: offline + calls routers")
else:
    print("SKIP: routers already mounted")

path.write_text(text, encoding="utf-8")
print("Done. New size:", len(text), "bytes")