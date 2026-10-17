"use client";
import { useEffect, useState } from "react";
const API = String(process.env.NEXT_PUBLIC_API_URL || "https://ai-growth-os-api.onrender.com").replace(/\/+$/, "");
type Tenant = { id: string; name: string; slug: string; industry: string; status: string };
export default function TenantServicesIndex() {
  const [items, setItems] = useState<Tenant[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) { window.location.href = "/login"; return; }
    fetch(API + "/api/v1/platform/tenants?limit=1000", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
      .then(async r => { const x = await r.json().catch(() => ({})); if (!r.ok) throw new Error(x.detail || "Could not load tenants."); return x; })
      .then(x => setItems(x.items || []))
      .catch(e => setError(e.message || "Could not load tenants."))
      .finally(() => setLoading(false));
  }, []);
  const filtered = items.filter(t => (t.name + " " + t.slug + " " + t.industry).toLowerCase().includes(search.toLowerCase()));
  return <main style={{ maxWidth: 1000, color: "#17213a" }}>
    <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: ".12em", color: "#5b5cf0" }}>SUPER ADMIN · CONFIGURATION</div>
    <h1 style={{ margin: "8px 0", fontSize: 28 }}>Tenant Services</h1>
    <p style={{ color: "#75839a", fontSize: 13 }}>Choose a tenant to enable or disable its individual services and features. Changes are isolated to the selected tenant.</p>
    <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search tenant, slug, or industry…" style={{ width: "100%", boxSizing: "border-box", padding: 12, border: "1px solid #d7dce5", borderRadius: 10, margin: "10px 0 16px" }} />
    {error && <p role="alert" style={{ color: "#b42318" }}>{error}</p>}
    {loading ? <p style={{ color: "#75839a" }}>Loading tenants…</p> : <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
      {filtered.map(t => <div key={t.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, padding: 16, borderBottom: "1px solid #f1f4f8", flexWrap: "wrap" }}>
        <div><strong>{t.name}</strong><div style={{ color: "#75839a", fontSize: 12, marginTop: 4 }}>{t.industry} · /{t.slug} · {t.status}</div></div>
        <a href={"/platform/tenants/" + encodeURIComponent(t.id) + "/services"} style={{ padding: "9px 13px", background: "#f4f3ff", borderRadius: 9, color: "#5145cd", textDecoration: "none", fontWeight: 700, fontSize: 12 }}>Manage services →</a>
      </div>)}
      {!filtered.length && <p style={{ padding: 20, color: "#75839a" }}>No matching tenants.</p>}
    </div>}
  </main>;
}
