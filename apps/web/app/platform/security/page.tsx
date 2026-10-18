"use client";
import { useEffect, useMemo, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Tenant = { id: string; name: string; slug: string; industry: string; status: string };
const FEATURE = "security_visitor_management";
const labelStyle: React.CSSProperties = { display: "block", color: "#667085", fontSize: 12, marginBottom: 6 };
const inputStyle: React.CSSProperties = { width: "100%", padding: "11px 12px", border: "1px solid #d9dfeb", borderRadius: 9, background: "#fff", color: "#17213a" };

export default function PlatformSecurityPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [defaults, setDefaults] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [tenantSearch, setTenantSearch] = useState("");
  const [searchField, setSearchField] = useState("all");
  const [statusFilter, setStatusFilter] = useState("");
  const [industryFilter, setIndustryFilter] = useState("");
  const [sortOrder, setSortOrder] = useState("newest");

  const selected = useMemo(() => tenants.find(t => t.id === tenantId), [tenants, tenantId]);
  const industries = useMemo(() => Array.from(new Set(tenants.map(t => (t.industry || "Unknown").trim()).filter(Boolean))).sort((a, b) => a.localeCompare(b)), [tenants]);
  const filteredTenants = useMemo(() => {
    const q = tenantSearch.trim().toLocaleLowerCase();
    return tenants.filter(t => {
      const name = (t.name || "").toLocaleLowerCase();
      const industry = (t.industry || "").toLocaleLowerCase();
      const slug = (t.slug || "").toLocaleLowerCase();
      const matchesQuery = !q || (searchField === "name" ? name.includes(q) :
        searchField === "industry" ? industry.includes(q) :
        searchField === "status" ? (t.status || "").toLocaleLowerCase().includes(q) :
        searchField === "slug" ? slug.includes(q) :
        name.includes(q) || industry.includes(q) || slug.includes(q) || (t.status || "").toLocaleLowerCase().includes(q));
      return matchesQuery && (!statusFilter || (t.status || "").toLowerCase() === statusFilter) &&
        (!industryFilter || (t.industry || "Unknown").trim() === industryFilter);
    }).sort((a, b) => sortOrder === "name" ? a.name.localeCompare(b.name) :
      sortOrder === "oldest" ? (a as any).created_at?.localeCompare((b as any).created_at || "") || 0 :
      ((b as any).created_at || "").localeCompare((a as any).created_at || ""));
  }, [tenants, tenantSearch, searchField, statusFilter, industryFilter, sortOrder]);
  const token = () => typeof window === "undefined" ? "" : localStorage.getItem("ago_access_token") || "";
  async function request(path: string, init: RequestInit = {}) {
    const response = await fetch(api() + path, {
      ...init,
      headers: { Authorization: "Bearer " + token(), ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers || {}) },
      cache: "no-store",
    });
    if (response.status === 401 || response.status === 403) { window.location.href = "/login"; throw new Error("auth"); }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || "Request failed");
    return body;
  }

  useEffect(() => {
    if (!token()) { window.location.href = "/login"; return; }
    Promise.all([
      request("/api/v1/platform/tenants?limit=500"),
      request("/api/v1/platform/feature-defaults"),
    ]).then(([t, d]) => {
      const rows = t.items || [];
      setTenants(rows);
      setDefaults(d.features || {});
      if (rows.length) setTenantId(rows[0].id);
    }).catch(e => { if (e.message !== "auth") setError(e.message); }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!tenantId || !token()) return;
    setError(""); setMessage("");
    Promise.all([
      request("/api/v1/platform/tenants/" + encodeURIComponent(tenantId) + "/overrides"),
      request("/api/v1/platform/feature-defaults"),
    ]).then(([o, d]) => {
      setDefaults(d.features || {});
      setFeatures({ ...(d.features || {}), ...(o.features || {}) });
    }).catch(e => { if (e.message !== "auth") setError(e.message); });
  }, [tenantId]);

  async function save() {
    if (!tenantId) return;
    setSaving(true); setError(""); setMessage("");
    try {
      const result = await request("/api/v1/platform/tenants/" + encodeURIComponent(tenantId) + "/overrides", {
        method: "PUT", body: JSON.stringify({ features }),
      });
      setFeatures({ ...defaults, ...(result.features || {}) });
      setMessage("Security service assignment saved.");
    } catch (e: any) { setError(e.message || "Save failed"); }
    finally { setSaving(false); }
  }

  if (loading) return <div style={{ padding: 40, color: "#75839a" }}>Loading tenant assignments…</div>;
  return <main style={{ maxWidth: 1000, margin: "0 auto", color: "#17213a" }}>
    <header style={{ marginBottom: 22 }}>
      <div style={{ color: "#5b5cf0", fontSize: 12, fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase" }}>Platform service control</div>
      <h1 style={{ margin: "7px 0", fontSize: 28, letterSpacing: "-.03em" }}>Security &amp; Visitors</h1>
      <p style={{ margin: 0, color: "#75839a", fontSize: 14 }}>Assign this service only to tenants who require it. Tenant data and visitor records are retained if the service is disabled.</p>
    </header>
    {error && <div role="alert" style={{ padding: 12, marginBottom: 14, background: "#fff1f1", color: "#b42318", borderRadius: 9 }}>{error}</div>}
    <section style={{ background: "#fff", border: "1px solid #e7ebf2", borderRadius: 14, padding: 22, marginBottom: 16 }}>
      <label htmlFor="tenant-search" style={labelStyle}>Find tenant</label>
      <div style={{ display: "grid", gridTemplateColumns: "minmax(220px, 2fr) repeat(auto-fit, minmax(145px, 1fr))", gap: 10, marginBottom: 12 }}>
        <input id="tenant-search" aria-label="Search tenants" placeholder="Search business, industry, status or slug…" value={tenantSearch} onChange={e => setTenantSearch(e.target.value)} style={inputStyle} />
        <select aria-label="Search field" value={searchField} onChange={e => setSearchField(e.target.value)} style={inputStyle}>
          <option value="all">Search all fields</option><option value="name">Business name</option><option value="industry">Industry type</option><option value="status">Status</option><option value="slug">Tenant slug</option>
        </select>
        <select aria-label="Filter industry" value={industryFilter} onChange={e => setIndustryFilter(e.target.value)} style={inputStyle}>
          <option value="">All industries</option>{industries.map(i => <option key={i} value={i}>{i}</option>)}
        </select>
        <select aria-label="Filter status" value={statusFilter} onChange={e => setStatusFilter(e.target.value)} style={inputStyle}>
          <option value="">All statuses</option><option value="active">Active</option><option value="suspended">Suspended</option><option value="pending">Pending</option><option value="closed">Closed</option>
        </select>
        <select aria-label="Sort tenants" value={sortOrder} onChange={e => setSortOrder(e.target.value)} style={inputStyle}>
          <option value="newest">Recently created</option><option value="oldest">Oldest created</option><option value="name">Business name A–Z</option>
        </select>
        <button type="button" onClick={() => { setTenantSearch(""); setSearchField("all"); setStatusFilter(""); setIndustryFilter(""); setSortOrder("newest"); }} style={{ ...inputStyle, cursor: "pointer", fontWeight: 600 }}>Clear filters</button>
      </div>
      <label htmlFor="tenant" style={labelStyle}>Select tenant ({filteredTenants.length} matches)</label>
      <select id="tenant" value={tenantId} onChange={e => setTenantId(e.target.value)} style={{ ...inputStyle, maxWidth: 560 }}>
        {filteredTenants.map(t => <option key={t.id} value={t.id}>{t.name} · {t.industry} · {t.status}</option>)}
      </select>
      {filteredTenants.length === 0 && <p style={{ color: "#b42318" }}>No tenants match these filters. Clear filters or try another search.</p>}
      {!tenants.length && <p style={{ color: "#b42318" }}>No tenants found.</p>}
      {selected && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <span style={{ padding: "5px 9px", borderRadius: 20, background: "#f1f3f9", fontSize: 12 }}>/{selected.slug}</span>
        <span style={{ padding: "5px 9px", borderRadius: 20, background: selected.status === "active" ? "#e8f8ef" : "#fff4df", color: selected.status === "active" ? "#18794e" : "#946200", fontSize: 12 }}>{selected.status}</span>
      </div>}
    </section>
    {selected && <section style={{ background: "#fff", border: "1px solid #e7ebf2", borderRadius: 14, padding: 22 }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 18, flexWrap: "wrap" }}>
        <div style={{ maxWidth: 650 }}>
          <h2 style={{ margin: "0 0 7px", fontSize: 17 }}>Security &amp; Visitor Management</h2>
          <p style={{ margin: 0, color: "#75839a", fontSize: 13, lineHeight: 1.6 }}>Enables visitor registration, QR entry workflow, human approval, and security logs for this tenant. Disabling blocks service access without deleting historical records.</p>
        </div>
        <span style={{ padding: "6px 10px", borderRadius: 20, background: features[FEATURE] ? "#e8f8ef" : "#f2f4f7", color: features[FEATURE] ? "#18794e" : "#667085", fontSize: 12, fontWeight: 700 }}>{features[FEATURE] ? "ASSIGNED" : "NOT ASSIGNED"}</span>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 12, padding: 16, border: "1px solid " + (features[FEATURE] ? "#a7e5c1" : "#e7ebf2"), borderRadius: 11, marginTop: 20, cursor: "pointer" }}>
        <input type="checkbox" checked={!!features[FEATURE]} onChange={e => setFeatures(f => ({ ...f, [FEATURE]: e.target.checked }))} style={{ width: 18, height: 18 }} />
        <span><strong style={{ display: "block", fontSize: 14 }}>Assign Security &amp; Visitor Management</strong><small style={{ display: "block", color: "#75839a", marginTop: 4 }}>Only affects {selected.name}; other tenant assignments remain unchanged.</small></span>
      </label>
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 20, flexWrap: "wrap" }}>
        <button onClick={save} disabled={saving} style={{ border: 0, borderRadius: 9, padding: "11px 18px", background: "#5b5cf0", color: "#fff", fontWeight: 700, cursor: saving ? "wait" : "pointer", opacity: saving ? .7 : 1 }}>{saving ? "Saving…" : "Save assignment"}</button>
        {message && <span role="status" style={{ color: "#18794e", fontSize: 13 }}>{message}</span>}
        <span style={{ color: "#98a2b3", fontSize: 12 }}>New-tenant default: {defaults[FEATURE] ? "enabled" : "disabled"}</span>
      </div>
    </section>}
  </main>;
}
