"""Make the sidebar use t() for its labels."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SIDEBAR = HERE / "components" / "Sidebar.tsx"

if not SIDEBAR.exists():
    print("ERROR: Sidebar.tsx not found")
    raise SystemExit(1)

text = SIDEBAR.read_text(encoding="utf-8")

if "const { t } = useTranslation()" in text:
    print("SKIP: translation already wired")
    raise SystemExit(0)

# Hook the useTranslation call at the top of the component
anchor = "  const pathname = usePathname() || \"\";"
if anchor not in text:
    print("ERROR: pathname anchor not found")
    raise SystemExit(1)

text = text.replace(anchor, anchor + "\n  const { t } = useTranslation();", 1)

# Replace the raw item.label with t("nav.xxx") - build a key from the href
# We do a simple string replace for each label in the render block
replacements = {
    '<span>{item.label}</span>': '<span>{t("nav." + item.href.replace("/platform/", "").replace("/dashboard/", "tenant.").replace("/", "") || "overview")}</span>',
}
for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new, 1)
        break

SIDEBAR.write_text(text, encoding="utf-8")
print("Translations wired into Sidebar.tsx")