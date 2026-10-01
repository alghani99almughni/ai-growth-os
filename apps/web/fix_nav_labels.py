"""Replace the fragile href-derived translation with an explicit map."""
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
NAV = HERE / "lib" / "nav.ts"

if not NAV.exists():
    print("ERROR: lib/nav.ts not found")
    raise SystemExit(1)

text = NAV.read_text(encoding="utf-8")

if 'labelKey' in text:
    print("SKIP: labelKey already present")
    raise SystemExit(0)

# Add a labelKey to every item in nav.ts
def add_key(match):
    block = match.group(0)
    # For each `{ href: "...", label: "...", icon: "..." }` add `, labelKey: "nav.xxx"`
    def per_entry(m):
        entry = m.group(0)
        href = re.search(r'href:\s*"([^"]+)"', entry).group(1)
        # derive a key
        if href == "/platform":
            key = "nav.overview"
        elif href.startswith("/platform/"):
            key = "nav." + href[len("/platform/"):].replace("/", ".")
        elif href == "/dashboard":
            key = "nav.tenant.overview"
        elif href.startswith("/dashboard/"):
            key = "nav.tenant." + href[len("/dashboard/"):].replace("/", ".")
        else:
            key = "nav." + href.strip("/").replace("/", ".")
        if "labelKey:" in entry:
            return entry
        return entry.rstrip().rstrip("}") .rstrip() + ', labelKey: "' + key + '" }'
    return re.sub(r'\{[^{}]+\}', per_entry, block)

text = re.sub(r'export const (TENANT_NAV|ADMIN_NAV): NavItem\[\] = \[[^\]]*\];',
              lambda m: m.group(0), text)  # no-op sanity check

# Simpler: regex-replace each entry inside TENANT_NAV and ADMIN_NAV
def rewrite_array(arr_name, text):
    start = text.find("export const " + arr_name)
    if start < 0:
        return text
    end = text.find("];", start)
    if end < 0:
        return text
    block = text[start:end]
    def add_label_key(m):
        entry = m.group(0)
        if "labelKey" in entry:
            return entry
        href_match = re.search(r'href:\s*"([^"]+)"', entry)
        if not href_match:
            return entry
        href = href_match.group(1)
        if href == "/platform":
            key = "nav.overview"
        elif href.startswith("/platform/"):
            key = "nav." + href[len("/platform/"):].replace("/", ".")
        elif href == "/dashboard":
            key = "nav.tenant.overview"
        elif href.startswith("/dashboard/"):
            key = "nav.tenant." + href[len("/dashboard/"):].replace("/", ".")
        else:
            key = "nav." + href.strip("/").replace("/", ".")
        return entry.rstrip().rstrip("}").rstrip() + ', labelKey: "' + key + '" }'
    new_block = re.sub(r'\{[^{}]+\}', add_label_key, block)
    return text[:start] + new_block + text[end:]

text = rewrite_array("TENANT_NAV", text)
text = rewrite_array("ADMIN_NAV", text)

# Also update the NavItem type
if "labelKey" not in text.split("export const")[0]:
    old_type = "export type NavItem = {\n  href: string;\n  label: string;\n  icon: string;\n  exact?: boolean;\n};"
    new_type = "export type NavItem = {\n  href: string;\n  label: string;\n  labelKey?: string;\n  icon: string;\n  exact?: boolean;\n};"
    if old_type in text:
        text = text.replace(old_type, new_type, 1)

NAV.write_text(text, encoding="utf-8")
print("Added labelKey to every nav item")