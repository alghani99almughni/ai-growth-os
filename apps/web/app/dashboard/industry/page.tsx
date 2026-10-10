"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Entry = { id: string; category: string; business_type: string; roles: string[]; is_active: boolean; sort_order: number };
type Selection = { catalog_entry_id: string; category: string; business_type: string; roles: string[]; notes?: string | null };
const input: React.CSSProperties = { width: "100%", padding: "11px 13px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, color: "#17213a", background: "#fff", boxSizing: "border-box" };
const card: React.CSSProperties = { background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22 };

export default function TenantIndustrySettings() {
  const [tenantId, setTenantId] = useState("");
  const [items, setItems] = useState<Entry[]>([]);
  const [entryId, setEntryId] = useState("");
  const [notes, setNotes] = useState("");
  const [current, setCurrent] = useState<Selection | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const token = localStorage.getItem("ago_access_token") || "";
    const res = await fetch(api() + path, { ...init, cache: "no-store", headers: {
      "Content-Type": "application/json", Authorization: "Bearer " + token, ...(init.headers || {}),
    }});
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 || res.status === 403) throw new Error("You do not have permission to update this tenant.");
    if (!res.ok) throw new Error(data.detail || "Request failed (" + res.status + ")");
    return data;
  }, []);

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) { window.location.href = "/login"; return; }
    let id = new URLSearchParams(window.location.search).get("tenant") || "";
    if (!id) {
      try { id = JSON.parse(localStorage.getItem("ago_tenant") || "{}").id || ""; } catch {}
    }
    if (!id) { window.location.href = "/onboarding"; return; }
    setTenantId(id);
    Promise.all([
      request("/api/v1/public/industry-catalog"),
      request("/api/v1/tenants/" + id + "/industry-selection"),
    ]).then(([catalog, selection]) => {
      const entries: Entry[] = catalog.items || [];
      setItems(entries);
      const saved: Selection | null = selection.selection || null;
      setCurrent(saved);
      if (saved?.catalog_entry_id) setEntryId(saved.catalog_entry_id);
      else if (entries.length) setEntryId(entries[0].id);
      setNotes(saved?.notes || "");
    }).catch((e) => setError(e instanceof Error ? e.message : "Could not load industry settings"))
      .finally(() => setLoading(false));
  }, [request]);

  const categories = useMemo(() => Array.from(new Set(items.map((x) => x.category)),), [items]);
  const selected = items.find((x) => x.id === entryId) || null;
  const subcategories = items.filter((x) => x.category === selected?.category);

  async function save() {
    if (!tenantId || !entryId) { setError("Select an industry category and business type first."); return; }
    setSaving(true); setError(""); setNotice("");
    try {
      const result = await request("/api/v1/tenants/" + tenantId + "/industry-selection", {
        method: "PUT", body: JSON.stringify({ catalog_entry_id: entryId, notes: notes.trim() || null }),
      });
      setCurrent(result.selection); setNotice("Industry selection saved. Existing services and tenant settings were not overwritten.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not save industry selection"); }
    finally { setSaving(false); }
  }

  return <main style={{ maxWidth: 900, margin: "0 auto", padding: "28px 22px 60px", color: "#17213a" }}>
    <div style={{ marginBottom: 22 }}><a href="/dashboard" style={{ color: "#5b5cf0", fontWeight: 700, fontSize: 12, textDecoration: "none" }}>← Dashboard</a>
      <h1 style={{ margin: "12px 0 6px", fontSize: 27, letterSpacing: "-.04em" }}>Industry & business type</h1>
      <p style={{ margin: 0, color: "#75839a", fontSize: 13 }}>Choose the global industry template that best matches your tenant. This selection does not overwrite your existing services, hours, staff, or feature settings.</p>
    </div>
    {error && <div role="alert" style={{ ...card, color: "#a52a2a", borderColor: "#f0b8b8", marginBottom: 14 }}>{error}</div>}
    {notice && <div role="status" style={{ ...card, color: "#16774d", borderColor: "#bdebd6", marginBottom: 14 }}>{notice}</div>}
    <section style={card}>
      {loading ? <p style={{ color: "#75839a" }}>Loading settings…</p> : <>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 16 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: "#5b667b" }}>Industry category
            <select value={selected?.category || ""} onChange={(e) => {
              const next = items.find((x) => x.category === e.target.value);
              setEntryId(next?.id || "");
            }} style={{ ...input, display: "block", marginTop: 7 }}>
              {categories.map((category) => <option key={category} value={category}>{category}</option>)}
            </select>
          </label>
          <label style={{ fontSize: 12, fontWeight: 700, color: "#5b667b" }}>Business type / subcategory
            <select value={entryId} onChange={(e) => setEntryId(e.target.value)} style={{ ...input, display: "block", marginTop: 7 }}>
              {subcategories.map((x) => <option key={x.id} value={x.id}>{x.business_type}</option>)}
            </select>
          </label>
        </div>
        {selected && <div style={{ marginTop: 20, padding: 16, background: "#f8f9fd", borderRadius: 10 }}>
          <h2 style={{ margin: "0 0 8px", fontSize: 14 }}>Suggested departments & roles</h2>
          <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}>{selected.roles.map((role) => <span key={role} style={{ borderRadius: 20, padding: "6px 9px", background: "#eef0ff", color: "#5653d8", fontSize: 11 }}>{role}</span>)}</div>
        </div>}
        <label style={{ display: "block", marginTop: 18, fontSize: 12, fontWeight: 700, color: "#5b667b" }}>Notes / custom requirements (optional)
          <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Add any tenant-specific department or workflow requirements…" style={{ ...input, display: "block", marginTop: 7, resize: "vertical" }} />
        </label>
        <button type="button" onClick={() => void save()} disabled={saving || !selected} style={{ marginTop: 18, border: 0, borderRadius: 9, padding: "11px 16px", background: "#5b5cf0", color: "#fff", fontWeight: 700, fontSize: 12, cursor: saving ? "wait" : "pointer", opacity: saving ? .6 : 1 }}>{saving ? "Saving…" : "Save industry selection"}</button>
        {current && <p style={{ color: "#75839a", fontSize: 12, marginTop: 14 }}>Currently saved: <strong>{current.category}</strong> / {current.business_type}</p>}
      </>}
    </section>
  </main>;
}
