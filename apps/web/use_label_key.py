"""Make Sidebar use labelKey when present."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SIDEBAR = HERE / "components" / "Sidebar.tsx"

if not SIDEBAR.exists():
    print("ERROR: Sidebar.tsx not found")
    raise SystemExit(1)

text = SIDEBAR.read_text(encoding="utf-8")

if "item.labelKey ? t(item.labelKey)" in text:
    print("SKIP: already patched")
    raise SystemExit(0)

old_candidates = [
    '<span>{t("nav." + item.href.replace("/platform/", "").replace("/dashboard/", "tenant.").replace("/", "") || "overview")}</span>',
    '<span>{item.label}</span>',
]

new = '<span>{item.labelKey ? t(item.labelKey) : item.label}</span>'

replaced = False
for old in old_candidates:
    if old in text:
        text = text.replace(old, new, 1)
        replaced = True
        print(f"Replaced: {old[:60]}...")
        break

if not replaced:
    print("WARNING: could not find the label span.")
    print("Search Sidebar.tsx for a line containing '<span>' inside the nav map.")
    print("Paste that line back and I'll send a targeted fix.")
    raise SystemExit(1)

SIDEBAR.write_text(text, encoding="utf-8")
print("Sidebar now uses labelKey")