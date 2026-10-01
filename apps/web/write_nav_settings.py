"""Add Settings to the ADMIN_NAV in lib/nav.ts."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "lib" / "nav.ts"

if not TARGET.exists():
    print("ERROR: lib/nav.ts not found")
    raise SystemExit(1)

text = TARGET.read_text(encoding="utf-8")

if "/platform/settings" in text:
    print("SKIP: Settings already in nav")
    raise SystemExit(0)

old = '  { href: "/platform/health",    label: "Health",            icon: "Activity" },'
new = old + '\n  { href: "/platform/settings",  label: "Settings",          icon: "Settings2" },'

if old not in text:
    print("ERROR: could not find the Health nav line")
    print("Expected to find:")
    print(repr(old))
    raise SystemExit(1)

text = text.replace(old, new, 1)
TARGET.write_text(text, encoding="utf-8")
print("Settings added to sidebar")