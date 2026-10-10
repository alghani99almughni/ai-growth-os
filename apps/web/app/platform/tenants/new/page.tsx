"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type CatalogEntry = { id: string; category: string; business_type: string; roles: string[]; is_active: boolean; sort_order: number };

export default function NewTenantPage() {
  const router = useRouter();

  const [businessName, setBusinessName] = useState("");
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [selectedEntryId, setSelectedEntryId] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [contactNumber, setContactNumber] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [website, setWebsite] = useState("");
  const [address, setAddress] = useState("");

  useEffect(() => {
    let active = true;
    fetch(`${API}/api/v1/public/industry-catalog`, { cache: "no-store" })
      .then((r) => { if (!r.ok) throw new Error("Industry catalogue unavailable"); return r.json(); })
      .then((x) => {
        if (!active) return;
        const entries: CatalogEntry[] = (x.items || []).filter((e: CatalogEntry) => e.is_active);
        setCatalog(entries);
        const firstCategory = entries[0]?.category || "";
        setSelectedCategory(firstCategory);
        setSelectedEntryId(entries.find((e) => e.category === firstCategory)?.id || "");
      })
      .catch(() => { if (active) setErr("Could not load active industry categories. Refresh the page or check the API."); })
      .finally(() => { if (active) setCatalogLoading(false); });
    return () => { active = false; };
  }, []);

  const categories = useMemo(() => Array.from(new Set(catalog.map((e) => e.category))).sort((a, b) => a.localeCompare(b)), [catalog]);
  const subcategories = useMemo(() => catalog.filter((e) => e.category === selectedCategory).sort((a, b) => a.sort_order - b.sort_order || a.business_type.localeCompare(b.business_type)), [catalog, selectedCategory]);
  const selectedEntry = catalog.find((e) => e.id === selectedEntryId) || null;

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setErr("");
    if (!selectedEntry) return setErr("Select an active industry category and subcategory first.");
    if (!businessName.trim()) return setErr("Business name is required.");
    if (!ownerName.trim() || !ownerEmail.trim() || ownerPassword.length < 8)
      return setErr("Owner name, email, and password (8+ chars) are required.");
    if (!contactNumber.trim()) return setErr("Contact number is required.");
    if (!whatsappNumber.trim()) return setErr("WhatsApp number is required.");

    setBusy(true);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : "";
      const res = await fetch(`${API}/api/v1/platform/tenants/provision`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          business_name: businessName.trim(),
          slug: null,
          industry: selectedEntry?.business_type || selectedCategory,
          catalog_entry_id: selectedEntry?.id || null,
          owner_name: ownerName.trim(),
          owner_email: ownerEmail.trim(),
          owner_password: ownerPassword,
          phone: contactNumber.trim(),
          whatsapp_number: whatsappNumber.trim(),
          address: address.trim() || null,
          website: website.trim() || null,
          template: null,
          business_hours: null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Unable to create tenant.");
      router.push(`/platform/tenants/${data.tenant.id}`);
    } catch (e: any) {
      setErr(String(e?.message || "Unable to create tenant."));
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ margin: "0 0 6px" }}>Create Tenant</h1>
      <p style={{ color: "#5a7268", marginTop: 0 }}>
        Provision a new business. Slug is generated automatically. Business hours and integrations are configured after creation.
      </p>

      <section style={{ display: "grid", gap: 12, marginBottom: 20 }}>
        <Field label="Business category">
          <select value={selectedCategory} disabled={catalogLoading || categories.length === 0} onChange={(e) => {
            const nextCategory = e.target.value;
            setSelectedCategory(nextCategory);
            setSelectedEntryId(catalog.find((entry) => entry.category === nextCategory)?.id || "");
          }} style={inp}>
            {catalogLoading && <option value="">Loading categories…</option>}
            {!catalogLoading && categories.length === 0 && <option value="">No active categories found</option>}
            {categories.map((category) => <option key={category} value={category}>{category}</option>)}
          </select>
        </Field>
        <Field label="Business subcategory">
          <select value={selectedEntryId} disabled={catalogLoading || subcategories.length === 0} onChange={(e) => setSelectedEntryId(e.target.value)} style={inp}>
            {subcategories.map((entry) => <option key={entry.id} value={entry.id}>{entry.business_type}</option>)}
          </select>
          {selectedEntry && selectedEntry.roles.length > 0 && <div style={{ fontSize: 11, color: "#75839a", marginTop: 4 }}>Suggested roles: {selectedEntry.roles.slice(0, 5).join(", ")}</div>}
        </Field>

        <Field label="Business name">
          <input value={businessName} onChange={(e) => setBusinessName(e.target.value)} placeholder="Test Biz" style={inp} />
        </Field>

        <hr style={{ border: 0, borderTop: "1px solid #e8ecf3", margin: "6px 0" }} />

        <Field label="Owner name">
          <input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} placeholder="Test Owner" style={inp} />
        </Field>

        <Field label="Owner email (used to sign in)">
          <input type="email" value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} placeholder="tenant@example.com" style={inp} />
        </Field>

        <Field label="Owner password (8+ characters)">
          <input type="password" value={ownerPassword} onChange={(e) => setOwnerPassword(e.target.value)} style={inp} />
        </Field>

        <hr style={{ border: 0, borderTop: "1px solid #e8ecf3", margin: "6px 0" }} />

        <Field label="Contact number">
          <input value={contactNumber} onChange={(e) => setContactNumber(e.target.value)} placeholder="+91 98765 43210" style={inp} />
        </Field>

        <Field label="WhatsApp number">
          <input value={whatsappNumber} onChange={(e) => setWhatsappNumber(e.target.value)} placeholder="+91 98765 43210" style={inp} />
        </Field>

        <Field label="Existing website (optional)">
          <input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://theirbusiness.com" style={inp} />
          <div style={{ fontSize: 11, color: "#75839a", marginTop: 4 }}>
            Leave blank if they don&apos;t have one — we&apos;ll generate a webpage for them.
          </div>
        </Field>

        <Field label="Address (optional)">
          <textarea value={address} onChange={(e) => setAddress(e.target.value)} rows={2} style={{ ...inp, fontFamily: "inherit" }} />
        </Field>
      </section>

      {err && <p style={{ color: "#b6341f", marginBottom: 12 }}>{err}</p>}

      <button
        disabled={busy}
        onClick={submit}
        style={{ padding: "12px 24px", background: "#1a5c43", color: "#fff", border: 0, borderRadius: 10, fontWeight: 700, fontSize: 14, cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1 }}
      >
        {busy ? "Creating…" : "Create Tenant"}
      </button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block" }}>
      <span style={{ display: "block", fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginBottom: 5 }}>{label}</span>
      {children}
    </label>
  );
}

const inp: React.CSSProperties = {
  display: "block", width: "100%", padding: "11px 13px", border: "1px solid #d7dce5",
  borderRadius: 9, fontSize: 14, color: "#17213a", background: "#fff", outline: "none", boxSizing: "border-box",
};