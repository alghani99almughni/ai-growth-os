"use client";

import { useCallback, useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Tenant = { id: string; name: string; slug?: string; industry?: string; status?: string };
type Connection = {
  tenant_id: string;
  script_url: string;
  drive_folder_url: string;
  legacy_tenant_code: string;
  script_status: string;
  drive_status: string;
  authenticated_sync_ready: boolean;
  note?: string;
};

const panel: React.CSSProperties = { background: "#fff", border: "1px solid #e2e7ef", borderRadius: 14, padding: 20 };
const inputStyle: React.CSSProperties = { width: "100%", boxSizing: "border-box", padding: "11px 12px", border: "1px solid #d5dce7", borderRadius: 9, fontSize: 13, marginTop: 7 };

export default function SmartCheckConnectionsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [scriptUrl, setScriptUrl] = useState("");
  const [driveUrl, setDriveUrl] = useState("");
  const [legacyTenantCode, setLegacyTenantCode] = useState("");
  const [status, setStatus] = useState<Connection | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const token = () => typeof window === "undefined" ? "" : localStorage.getItem("ago_access_token") || "";

  const loadConnection = useCallback(async (id: string) => {
    if (!id) return;
    setError(""); setMessage(""); setStatus(null);
    try {
      const response = await fetch(api() + "/api/v1/platform/tenants/" + encodeURIComponent(id) + "/smartcheck-connection", {
        headers: { Authorization: "Bearer " + token() }, cache: "no-store",
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Could not load connection settings");
      const data = await response.json() as Connection;
      setStatus(data); setScriptUrl(data.script_url || ""); setDriveUrl(data.drive_folder_url || ""); setLegacyTenantCode(data.legacy_tenant_code || "");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load connection settings"); }
  }, []);

  useEffect(() => {
    const accessToken = token();
    if (!accessToken) { window.location.href = "/login"; return; }
    fetch(api() + "/api/v1/platform/tenants", { headers: { Authorization: "Bearer " + accessToken }, cache: "no-store" })
      .then(async (r) => { if (!r.ok) throw new Error("Unable to load tenants; check platform administrator access"); return r.json(); })
      .then((data) => {
        const list: Tenant[] = data.items || [];
        setTenants(list);
        if (list.length) setTenantId(list[0].id);
        setLoading(false);
      })
      .catch((e) => { setError(e instanceof Error ? e.message : "Unable to load tenants"); setLoading(false); });
  }, []);

  useEffect(() => { if (tenantId) void loadConnection(tenantId); }, [tenantId, loadConnection]);

  async function saveAndCheck() {
    if (!tenantId) { setError("Select a tenant first."); return; }
    setSaving(true); setError(""); setMessage("");
    try {
      const response = await fetch(api() + "/api/v1/platform/tenants/" + encodeURIComponent(tenantId) + "/smartcheck-connection", {
        method: "POST",
        headers: { Authorization: "Bearer " + token(), "Content-Type": "application/json" },
        body: JSON.stringify({ script_url: scriptUrl.trim(), drive_folder_url: driveUrl.trim() || null, legacy_tenant_code: legacyTenantCode.trim() || null }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Could not save connection");
      setStatus({ tenant_id: tenantId, script_url: scriptUrl.trim(), drive_folder_url: driveUrl.trim(), legacy_tenant_code: legacyTenantCode.trim(), ...data });
      setLegacyTenantCode(data.legacy_tenant_code || legacyTenantCode.trim());
      setMessage("Settings saved. Review the statuses below; full sync is not yet enabled.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save connection"); }
    finally { setSaving(false); }
  }

  const badge = (value: string) => {
    const color = value === "reachable" ? "#16794b" : value === "link_saved_unverified" ? "#8a6100" : "#596579";
    return <span style={{ display: "inline-block", fontSize: 12, borderRadius: 20, padding: "5px 9px", background: "#f1f4f8", color }}>{value.replaceAll("_", " ")}</span>;
  };

  return <main style={{ maxWidth: 980, margin: "0 auto", padding: "8px 0 40px", color: "#17213a" }}>
    <div style={{ marginBottom: 22 }}>
      <div style={{ fontSize: 11, letterSpacing: ".12em", textTransform: "uppercase", color: "#738199", fontWeight: 700 }}>Platform configuration</div>
      <h1 style={{ margin: "7px 0", fontSize: 27, letterSpacing: "-.03em" }}>Security & Visitor Management</h1>
      <p style={{ margin: 0, color: "#69778d", fontSize: 14 }}>Connect the existing SmartCheck Apps Script for a selected tenant. Existing visitor workflows are not changed by saving these settings.</p>
    </div>
    {error && <div role="alert" style={{ ...panel, borderColor: "#efb4b4", color: "#a52626", marginBottom: 14 }}>{error}</div>}
    {message && <div role="status" style={{ ...panel, color: "#246a49", marginBottom: 14 }}>{message}</div>}
    <section style={{ ...panel, marginBottom: 16 }}>
      <label style={{ display: "block", fontWeight: 650, fontSize: 13 }}>Tenant
        <select value={tenantId} onChange={(e) => setTenantId(e.target.value)} disabled={loading || !tenants.length} style={inputStyle}>
          {loading && <option value="">Loading tenants…</option>}
          {!loading && tenants.length === 0 && <option value="">No tenants available</option>}
          {tenants.map((tenant) => <option key={tenant.id} value={tenant.id}>{tenant.name}{tenant.industry ? " · " + tenant.industry : ""}</option>)}
        </select>
      </label>
    </section>
    <section style={{ ...panel, marginBottom: 16 }}>
      <h2 style={{ margin: "0 0 6px", fontSize: 17 }}>1. SmartCheck Apps Script</h2>
      <p style={{ margin: "0 0 14px", color: "#69778d", fontSize: 13 }}>Paste the deployed Google Apps Script Web App URL ending in <code>/exec</code>. The check tests the public health endpoint only.</p>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600 }}>Web App URL
        <input value={scriptUrl} onChange={(e) => setScriptUrl(e.target.value)} placeholder="https://script.google.com/macros/s/…/exec" style={inputStyle} />
      </label>
      {status && <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}><strong style={{ fontSize: 13 }}>Health status</strong>{badge(status.script_status)}<span style={{ color: "#69778d", fontSize: 12 }}>Reachable does not mean authenticated sync is ready.</span></div>}
    </section>
    <section style={{ ...panel, marginBottom: 16 }}>
      <h2 style={{ margin: "0 0 6px", fontSize: 17 }}>2. Google Drive folder (optional)</h2>
      <p style={{ margin: "0 0 14px", color: "#69778d", fontSize: 13 }}>Save the folder link for reference. A sharing link alone does not authorize the platform to read or write Drive files.</p>
      <label style={{ display: "block", fontSize: 13, fontWeight: 600 }}>Drive folder URL
        <input value={driveUrl} onChange={(e) => setDriveUrl(e.target.value)} placeholder="https://drive.google.com/drive/folders/…" style={inputStyle} />
      </label>
      <label style={{ display: "block", marginTop: 14, fontSize: 13, fontWeight: 600 }}>Existing SmartCheck tenant code (optional)
        <input value={legacyTenantCode} onChange={(e) => setLegacyTenantCode(e.target.value)} placeholder="For example, TNT-101" maxLength={100} style={inputStyle} />
        <span style={{ display: "block", marginTop: 5, fontSize: 12, color: "#69778d", fontWeight: 400 }}>Maps this AI Growth OS tenant to its existing SmartCheck row. Each legacy code can map to only one tenant. Saving the mapping does not enable sync by itself.</span>
      </label>
      {status && <div style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "center" }}><strong style={{ fontSize: 13 }}>Drive status</strong>{badge(status.drive_status)}</div>}
    </section>
    <section style={{ ...panel, background: "#f8fafc" }}>
      <div style={{ fontWeight: 700, fontSize: 14 }}>Sync readiness</div>
      <div style={{ marginTop: 8, fontSize: 13, color: "#69778d" }}>Authenticated bridge handshake, tenant-code mapping, and authorized Drive read/write verification are not implemented in this stage.</div>
      <div style={{ marginTop: 12 }}>{badge("sync pending")}</div>
      <button onClick={saveAndCheck} disabled={saving || loading || !tenantId} style={{ marginTop: 18, padding: "11px 16px", border: 0, borderRadius: 9, background: saving ? "#8b96a8" : "#1d4ed8", color: "#fff", fontWeight: 650, cursor: saving ? "wait" : "pointer" }}>{saving ? "Saving and checking…" : "Save & Check Connection"}</button>
    </section>
  </main>;
}
