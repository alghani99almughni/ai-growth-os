"""Add the QR panel to app/dashboard/page.tsx."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
PAGE = HERE / "app" / "dashboard" / "page.tsx"

if not PAGE.exists():
    print("ERROR: app/dashboard/page.tsx not found.")
    sys.exit(1)

text = PAGE.read_text(encoding="utf-8")

if "QrPanel" in text:
    print("SKIP: QrPanel already imported")
    sys.exit(0)

# 1. Add import after the first "use client" or first import line
old_import = 'import {useEffect,useState} from "react";'
if old_import not in text:
    print("ERROR: could not find the React import line")
    sys.exit(1)

new_import = (
    'import {useEffect,useState} from "react";\n'
    'import QrPanel from "../../components/QrPanel";'
)
text = text.replace(old_import, new_import, 1)
print("  added QrPanel import")

# 2. Insert the QR tab render before the reviews tab block
reviews_marker = '{tab==="reviews"&&'
if reviews_marker not in text:
    print("WARNING: could not find the reviews tab block")
else:
    qr_render = (
        '{tab==="qr"&&tenant&&<QrPanel tenantId={tenant.id} '
        'token={localStorage.getItem("ago_access_token")||""}/>}\n'
    )
    text = text.replace(reviews_marker, qr_render + reviews_marker, 1)
    print("  added QR tab render")

# 3. Add "qr" to the navigation tab list
nav_old = '"whatsapp","integrations","social","reviews"'
nav_new = '"whatsapp","qr","integrations","social","reviews"'
if nav_old in text:
    text = text.replace(nav_old, nav_new, 1)
    print('  added "qr" to nav tabs')
else:
    print('  WARNING: nav line pattern not matched')
    print('  Search manually for the tab list and add "qr" between "whatsapp" and "integrations"')

PAGE.write_text(text, encoding="utf-8")
print()
print("Dashboard patched.")