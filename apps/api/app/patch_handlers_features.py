"""Add feature-flag enforcement to intent_handlers.py.

Blueprint: 'Feature flags must be enforced in the backend, not only hidden
in the UI.'

This patch:
1. Imports feature_gate helpers.
2. Adds a _feature_enabled(db, tenant, key) convenience wrapper.
3. Inserts checks at the top of 7 handlers that should be gated.

Handlers that stay always-on (informational or safety):
    business_hours, location, staff_info, callback_request,
    complaint, policy, refund, emergency
"""

import pathlib

path = pathlib.Path("intent_handlers.py")
text = path.read_text(encoding="utf-8")

if "_feature_enabled" in text:
    print("SKIP: already patched")
    raise SystemExit(0)

# ---------------------------------------------------------------------------
# 1. Add import + helper after the logger definition.
# ---------------------------------------------------------------------------

anchor = "logger = logging.getLogger(__name__)\n"

helper = '''logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature gate helper
# ---------------------------------------------------------------------------

def _feature_enabled(db, tenant, key, default=True):
    """Return whether a feature is enabled for this tenant.

    Reads from feature_gate.get_features which layers:
    platform defaults -> industry defaults -> platform override -> tenant override.
    """
    try:
        from .feature_gate import feature_enabled
        return feature_enabled(db, tenant.id, key, default)
    except Exception:
        # If anything fails, be permissive to avoid blocking real requests.
        return True


'''

if anchor not in text:
    print("ERROR: logger anchor not found")
    raise SystemExit(1)

text = text.replace(anchor, helper, 1)

# ---------------------------------------------------------------------------
# 2. Insert feature checks at the top of each gated handler.
#    We match the def line + the docstring's first line + the try: line,
#    then insert the check right after the try: line.
# ---------------------------------------------------------------------------

GATES = [
    ("handle_availability",   "bookings"),
    ("handle_booking_status", "bookings"),
    ("handle_booking_cancel", "bookings"),
    ("handle_order_status",   "online_ordering"),
    ("handle_delay_query",    "online_ordering"),
    ("handle_human_handoff",  "human_handoff"),
]

applied = 0

for handler_name, feature_key in GATES:
    # Locate the handler's def line
    marker = f"async def {handler_name}("
    idx = text.find(marker)
    if idx < 0:
        print(f"  SKIP {handler_name}: not found")
        continue

    # Find the try: line after the def (first occurrence after def)
    try_idx = text.find("    try:\n", idx)
    if try_idx < 0:
        print(f"  SKIP {handler_name}: no try block")
        continue

    insert_at = try_idx + len("    try:\n")

    # Check if already has a feature check (idempotency)
    snippet = text[idx:insert_at + 200]
    if f'"{feature_key}"' in snippet or f"'{feature_key}'" in snippet:
        print(f"  SKIP {handler_name}: already gated")
        continue

    check = (
        f'        if not _feature_enabled(db, tenant, "{feature_key}"):\n'
        f'            return None\n'
    )

    text = text[:insert_at] + check + text[insert_at:]
    applied += 1
    print(f"  ADDED gate to {handler_name} ({feature_key})")

# ---------------------------------------------------------------------------
# 3. handle_pricing uses show_pricing, which lives on tenant object, not
#    the same layered config. We check it directly.
# ---------------------------------------------------------------------------

pricing_marker = "async def handle_pricing("
pidx = text.find(pricing_marker)
if pidx >= 0:
    try_idx = text.find("    try:\n", pidx)
    if try_idx > 0:
        insert_at = try_idx + len("    try:\n")
        snippet = text[pidx:insert_at + 200]
        if "show_pricing" not in snippet:
            check = (
                "        # Prices are shown only when the tenant enabled show_pricing.\n"
                "        try:\n"
                "            from .feature_gate import feature_enabled as _fe\n"
                "            if not _fe(db, tenant.id, \"show_pricing\", False):\n"
                "                return None\n"
                "        except Exception:\n"
                "            pass\n"
            )
            text = text[:insert_at] + check + text[insert_at:]
            applied += 1
            print(f"  ADDED gate to handle_pricing (show_pricing)")
        else:
            print("  SKIP handle_pricing: already gated")
else:
    print("  SKIP handle_pricing: not found")

path.write_text(text, encoding="utf-8")
print(f"Done. {applied} gates added.")
print("New size:", len(text), "bytes")