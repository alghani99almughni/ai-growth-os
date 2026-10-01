"""Add Tickets, Messages, Calendar to the platform sidebar in lib/nav.ts."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
NAV = HERE / "lib" / "nav.ts"

if not NAV.exists():
    print("ERROR: lib/nav.ts not found. Run from apps/web.")
    sys.exit(1)

text = NAV.read_text(encoding="utf-8")

if "/platform/tickets" in text:
    print("SKIP: Tickets already in nav")
    sys.exit(0)

# Find the ADMIN_NAV block
start = text.find("export const ADMIN_NAV")
if start < 0:
    print("ERROR: ADMIN_NAV not found")
    sys.exit(1)

end = text.find("];", start)
if end < 0:
    print("ERROR: end of ADMIN_NAV not found")
    sys.exit(1)

block = text[start:end]

# Insert Tickets, Messages, Calendar before the closing bracket
new_entries = (
    '  { href: "/platform/tickets",   label: "Tickets",            icon: "LifeBuoy" },\n'
    '  { href: "/platform/messages",  label: "Messages",           icon: "MessageSquare" },\n'
    '  { href: "/platform/calendar",  label: "Calendar",           icon: "CalendarDays" },\n'
)

# Find the trailing newline + spaces before the ];
insertion_point = block.rstrip()
if insertion_point.endswith(","):
    new_block = insertion_point + "\n" + new_entries
else:
    new_block = insertion_point + ",\n" + new_entries

text = text[:start] + new_block + text[end:]
NAV.write_text(text, encoding="utf-8")
print("Added Tickets, Messages, Calendar to ADMIN_NAV")