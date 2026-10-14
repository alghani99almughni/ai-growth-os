"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API = String(process.env.NEXT_PUBLIC_API_URL || "https://ai-growth-os-api.onrender.com").replace(/\/+$/, "");
const GROUPS = [
  { title: "AI Engagement", items: [["ai_chat", "AI Chat"], ["ai_voice", "AI Voice & Calls"]] },
  { title: "Customer Services", items: [["bookings", "Bookings & Appointments"], ["digital_menu", "Digital Menu"], ["online_ordering", "Online Ordering"], ["order_tracking", "Order Tracking"], ["service_requests", "Service Requests"], ["call_waiter", "Call Staff / Waiter"], ["queue", "Queue Management"], ["online_payment", "Online Payments"], ["auto_bill", "Automatic Billing"]] },
  { title: "Growth & Retention", items: [["loyalty", "Loyalty & Rewards"], ["referrals", "Referrals"], ["feedback", "Customer Feedback"], ["google_review", "Google Reviews"], ["games", "Mini Games"]] },
  { title: "Security & Visitor Operations", items: [["security_visitor_management", "Security & Visitor Management"]] },
] as const;
type Features = Record<string, boolean>;
type Tenant = { id: string; name: string; industry: string; status: string };

export default function TenantServicesPage() {
  const params = useParams();
  const tenantId = String(params?.id || "");
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [features, setFeatures] = useState<Features>({});
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const access = localStorage.getItem("ago_access_token") || "";
    setToken(access);
    if (!access) { window.location.href = "/login"; return; }
    const headers = { Authorization: "Bearer " + access };
    Promise.all([
      fetch(API + "/api/v1/platform/tenants/" + encodeURIComponent(tenantId) + "/detail", { headers, cache: "no-store" }),
      fetch(API + "/api/v1/platform/feature-defaults", { headers, cache: "no-store" }),
      fetch(API + "/api/v1/platform/tenants/" + encodeURIComponent(tenantId) + "/overrides", { headers, cache: "no-store" }),
    ]).then(async ([tenantRes, defaultsRes, overridesRes]) => {
      const t = await tenantRes.json().catch(() => ({}));
      const d = await defaultsRes.json().catch(() => ({}));
      const o = await overridesRes.json().catch(() => ({}));
      if (!tenantRes.ok) throw new Error(t.detail || "Could not load tenant.");
      if (!defaultsRes.ok) throw new Error(d.detail || "Could not load platform feature defaults.");
      if (!overridesRes.ok) throw new Error(o.detail || "Could not load this tenant's service assignments.");
      setTenant(t);
      setFeatures({ ...(d.features || {}), ...(o.features || {}) });
    }).catch(e => setError(e.message || "Unable to load service assignments."))
      .finally(() => setLoading(false));
  }, [tenantId]);

  async function save() {
    setSaving(true); setError(""); setNotice("");
    try {
      const r = await fetch(API + "/api/v1/platform/tenants/" + encodeURIComponent(tenantId) + "/overrides", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({ features }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "Could not save tenant services.");
      setFeatures(old => ({ ...old, ...(data.features || {}) }));
      setNotice("Tenant service assignments saved.");
    } catch (e: any) { setError(e?.message || "Save failed."); }
    finally { setSaving(false); }
  }

  if (loading) return <div style={{ padding: 40, color: "#75839a" }}>Loading tenant services…</div>;
  if (error && !tenant) return <div role="alert" style={{ padding: 24, color: "#b42318" }}>{error}</div>;

  const enabledCount = Object.values(features).filter(Boolean).length;
  return <main style={{ maxWidth: 1000, color: "#17213a" }}>
    <a href="/platform/tenants" style={{ color: "#5b5cf0", textDecoration: "none", fontSize: 13 }}>← Back to tenants</a>
    <header style={{ margin: "16px 0 24px" }}>
      <div style={{ fontSize: 11, letterSpacing: ".12em", fontWeight: 800, color: "#5b5cf0" }}>SUPER ADMIN · TENANT CONFIGURATION</div>
      <h1 style={{ margin: "7px 0", fontSize: 28 }}>Services & Features</h1>
      <p style={{ color: "#75839a", margin: 0 }}>{tenant?.name || "Tenant"} · {tenant?.industry || "Industry"} · {enabledCount} enabled</p>
      <p style={{ color: "#75839a", fontSize: 13 }}>Changes apply only to this tenant. Platform defaults for other tenants remain unchanged.</p>
    </header>
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))", gap: 14 }}>
      {GROUPS.map(group => <section key={group.title} style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18 }}>
        <h2 style={{ fontSize: 15, margin: "0 0 14px" }}>{group.title}</h2>
        <div style={{ display: "grid", gap: 9 }}>
          {group.items.map(([key, label]) => <label key={key} style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 10px", border: "1px solid " + (features[key] ? "#c8c8ff" : "#e8ecf3"), background: features[key] ? "#f7f6ff" : "#fff", borderRadius: 9, cursor: "pointer" }}>
            <input type="checkbox" checked={!!features[key]} onChange={e => setFeatures(old => ({ ...old, [key]: e.target.checked }))} />
            <span style={{ fontSize: 13 }}>{label}</span>
            <span style={{ marginLeft: "auto", fontSize: 10, color: features[key] ? "#21865b" : "#8b95a5", fontWeight: 700 }}>{features[key] ? "ENABLED" : "DISABLED"}</span>
          </label>)}
        </div>
      </section>)}
    </div>
    <p style={{ color: "#75839a", fontSize: 12, marginTop: 16 }}>Enabling a feature controls platform availability; external providers such as WhatsApp, email, and payments still require their own connection and credential setup.</p>
    {error && <p role="alert" style={{ color: "#b42318" }}>{error}</p>}
    {notice && <p role="status" style={{ color: "#21865b" }}>{notice}</p>}
    <button onClick={save} disabled={saving} style={{ marginTop: 8, padding: "12px 24px", background: "#5b5cf0", color: "#fff", border: 0, borderRadius: 10, fontWeight: 700, cursor: saving ? "wait" : "pointer" }}>{saving ? "Saving…" : "Save service assignments"}</button>
  </main>;
}
