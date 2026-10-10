"use client";

import { useEffect, useMemo, useState } from "react";
import WhatsappPanel from "../../../components/WhatsappPanel";
import EmailPanel from "../../../components/EmailPanel";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
type Tenant = { id: string; name: string; slug: string; industry: string; status: string };
type Tab = "whatsapp" | "email";

export default function PlatformIntegrationsPage() {
  const [tab, setTab] = useState<Tab>("whatsapp");
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const accessToken = localStorage.getItem("ago_access_token") || "";
    setToken(accessToken);
    if (!accessToken) {
      setError("Your Super Admin session is missing. Sign in again.");
      setLoading(false);
      return;
    }
    fetch(API + "/api/v1/platform/tenants", {
      headers: { Authorization: "Bearer " + accessToken },
      cache: "no-store",
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(r.status === 403 ? "Super Admin access is required." : "Could not load tenants.");
        return r.json();
      })
      .then((data) => {
        if (!active) return;
        const rows: Tenant[] = data.items || [];
        setTenants(rows);
        setTenantId((current) => current || rows[0]?.id || "");
        if (!rows.length) setError("No tenants are available yet. Create a tenant first.");
      })
      .catch((e) => { if (active) setError(e.message || "Could not load tenants."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const selectedTenant = useMemo(() => tenants.find((t) => t.id === tenantId), [tenants, tenantId]);

  return (
    <div>
      <header style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Tenant integrations</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Use the same WhatsApp and Email tools available in the tenant dashboard, from Super Admin.
        </p>
      </header>
      <section style={{ background: "#fff", border: "1px solid #e3e8f0", borderRadius: 14, padding: 16, marginBottom: 18, maxWidth: 900 }}>
        <label htmlFor="integration-tenant" style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#536174", marginBottom: 7 }}>Business / tenant</label>
        <select id="integration-tenant" value={tenantId} disabled={loading || tenants.length === 0} onChange={(e) => setTenantId(e.target.value)}
          style={{ width: "100%", maxWidth: 520, padding: "11px 12px", border: "1px solid #d5dce7", borderRadius: 9, background: "#fff", color: "#17213a" }}>
          {tenants.map((t) => <option key={t.id} value={t.id}>{t.name} — {t.industry || "Uncategorised"} ({t.status})</option>)}
        </select>
        {selectedTenant && <p style={{ margin: "8px 0 0", fontSize: 12, color: "#75839a" }}>Selected: {selectedTenant.name} · {selectedTenant.slug}</p>}
      </section>
      <nav aria-label="Integration type" style={{ display: "flex", gap: 8, borderBottom: "1px solid #e3e8f0", marginBottom: 18 }}>
        <button type="button" onClick={() => setTab("whatsapp")} aria-pressed={tab === "whatsapp"} style={tabButton(tab === "whatsapp")}>WhatsApp</button>
        <button type="button" onClick={() => setTab("email")} aria-pressed={tab === "email"} style={tabButton(tab === "email")}>Email</button>
      </nav>
      {loading && <p style={{ color: "#75839a" }}>Loading tenant integrations…</p>}
      {!loading && error && <p role="alert" style={{ color: "#b42318", background: "#fff5f4", padding: 12, borderRadius: 8 }}>{error}</p>}
      {!loading && !error && selectedTenant && token && (tab === "whatsapp"
        ? <WhatsappPanel tenantId={tenantId} token={token} />
        : <EmailPanel tenantId={tenantId} token={token} />)}
    </div>
  );
}

function tabButton(active: boolean): React.CSSProperties {
  return { appearance: "none", border: 0, borderBottom: active ? "2px solid #1a5c43" : "2px solid transparent", background: "transparent", color: active ? "#1a5c43" : "#75839a", padding: "11px 15px", marginBottom: -1, fontSize: 13, fontWeight: 700, cursor: "pointer" };
}
