"""Ensure Sidebar.tsx imports the icons used by nav.ts."""
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
SIDEBAR = HERE / "components" / "Sidebar.tsx"

if not SIDEBAR.exists():
    print("ERROR: components/Sidebar.tsx not found")
    raise SystemExit(1)

text = SIDEBAR.read_text(encoding="utf-8")

NEEDED = [
    "LayoutDashboard", "Phone", "QrCode", "ClipboardList", "CalendarDays", "Users",
    "ShoppingBag", "UserCog", "Brain", "Gift", "MessageCircle", "Globe", "Bot", "Star",
    "AlertTriangle", "Settings2", "Building2", "ToggleLeft", "FileText", "Activity",
    "Sparkles", "LogOut", "X", "LifeBuoy", "MessageSquare",
]

match = re.search(r'import\s*\{([^}]+)\}\s*from\s*"lucide-react"\s*;', text)
if not match:
    print("ERROR: lucide-react import not found in Sidebar.tsx")
    raise SystemExit(1)

existing = {x.strip() for x in match.group(1).split(",") if x.strip()}
missing = [x for x in NEEDED if x not in existing]

if not missing:
    print("SKIP: all icons already imported")
    raise SystemExit(0)

combined = sorted(existing | set(NEEDED))
new_import = "import {\n  " + ",\n  ".join(combined) + ",\n} from \"lucide-react\";"
text = text[:match.start()] + new_import + text[match.end():]

icons_map_match = re.search(r'const ICONS: Record<string, any> = \{([^}]+)\};', text)
if icons_map_match:
    entries = {x.strip() for x in icons_map_match.group(1).split(",") if x.strip()}
    for name in NEEDED:
        entries.add(name)
    new_map = "const ICONS: Record<string, any> = {\n  " + ",\n  ".join(sorted(entries)) + ",\n};"
    text = text[:icons_map_match.start()] + new_map + text[icons_map_match.end():]

SIDEBAR.write_text(text, encoding="utf-8")
print(f"Updated Sidebar.tsx — added {len(missing)} icon(s): {', '.join(missing)}")