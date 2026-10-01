"""Add a language toggle to Sidebar.tsx."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SIDEBAR = HERE / "components" / "Sidebar.tsx"

if not SIDEBAR.exists():
    print("ERROR: Sidebar.tsx not found")
    raise SystemExit(1)

text = SIDEBAR.read_text(encoding="utf-8")

if "ago-lang-change" in text or "LanguageToggle" in text:
    print("SKIP: language toggle already present")
    raise SystemExit(0)

# Add the import for the hook
if "useTranslation" not in text:
    # After the nav import line
    anchor = 'import { TENANT_NAV, ADMIN_NAV, type NavItem } from "../lib/nav";'
    if anchor not in text:
        print("ERROR: nav import anchor not found")
        raise SystemExit(1)
    text = text.replace(anchor, anchor + '\nimport { LANGUAGES, useTranslation, setLang } from "../lib/i18n";', 1)

# Add the toggle component before the last "Sign out" button
anchor = '''          <button
            onClick={onLogout}'''
if anchor not in text:
    print("ERROR: logout button anchor not found")
    raise SystemExit(1)

toggle = '''          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: "#7186a6", fontWeight: 800, letterSpacing: "0.12em", marginBottom: 6 }}>LANGUAGE</div>
            <select
              value={typeof window !== "undefined" ? localStorage.getItem("ago_lang") || "en" : "en"}
              onChange={(e) => setLang(e.target.value)}
              style={{
                width: "100%",
                background: "#0d2744",
                color: "#dce6f8",
                border: "1px solid #1c4164",
                borderRadius: 8,
                padding: "8px 10px",
                fontSize: 12,
              }}
            >
              {LANGUAGES.map((l: any) => (
                <option key={l.code} value={l.code}>{l.native}</option>
              ))}
            </select>
          </div>
'''

text = text.replace(anchor, toggle + anchor, 1)

SIDEBAR.write_text(text, encoding="utf-8")
print("Language toggle added to Sidebar.tsx")