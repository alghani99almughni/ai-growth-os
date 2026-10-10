"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Entry = { id: string; category: string; business_type: string; roles: string[]; is_active: boolean; sort_order: number };
const blank = (): Omit<Entry, "id"> => ({ category: "", business_type: "", roles: [], is_active: true, sort_order: 100 });
const panel: React.CSSProperties = { background: "#fff", border: "1px solid #e7ebf3", borderRadius: 14, padding: 20 };
const label: React.CSSProperties = { display: "block", color: "#5b667b", fontSize: 12, fontWeight: 700, marginBottom: 6 };
const input: React.CSSProperties = { width: "100%", border: "1px solid #dce2ec", borderRadius: 9, padding: "10px 12px", fontSize: 13, color: "#18243b", outlineColor: "#6865ed", background: "#fff" };
const button: React.CSSProperties = { border: 0, borderRadius: 9, padding: "10px 14px", background: "#5b5cf0", color: "#fff", fontSize: 12, fontWeight: 700, cursor: "pointer" };

export default function IndustryCatalogPage() {
  const [items, setItems] = useState<Entry[]>([]);
  const [draft, setDraft] = useState<Omit<Entry, "id">>(blank());
  const [editingId, setEditingId] = useState("");
  const [rolesText, setRolesText] = useState("");
  const [query, setQuery] = useState("");
  const [showInactive, setShowInactive] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const token = () => typeof window === "undefined" ? "" : localStorage.getItem("ago_access_token") || "";
  const request = useCallback(async (path: string, init: RequestInit = {}) => {
    const res = await fetch(api() + path, { ...init, cache: "no-store", headers: {
      "Content-Type": "application/json", Authorization: "Bearer " + token(), ...(init.headers || {}),
    }});
    if (res.status === 401 || res.status === 403) { window.location.href = "/login"; throw new Error("Platform admin login required."); }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail || "Request failed (" + res.status + ")");
    return body;
  }, []);

  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const result = await request("/api/v1/platform/industry-catalog?include_inactive=true"); setItems(result.items || []); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load catalogue"); }
    finally { setLoading(false); }
  }, [request]);

  useEffect(() => { if (!token()) { window.location.href = "/login"; return; } void load(); }, [load]);

  const visible = useMemo(() => items.filter((x) => (showInactive || x.is_active) &&
    (x.category + " " + x.business_type + " " + x.roles.join(" ")).toLowerCase().includes(query.toLowerCase()))
    .sort((a, b) => a.sort_order - b.sort_order || a.category.localeCompare(b.category) || a.business_type.localeCompare(b.business_type)), [items, query, showInactive]);

  function edit(item: Entry) {
    setEditingId(item.id);
    setDraft({ category: item.category, business_type: item.business_type, roles: item.roles, is_active: item.is_active, sort_order: item.sort_order });
    setRolesText(item.roles.join(", "));
    setNotice(""); setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function reset() { setEditingId(""); setDraft(blank()); setRolesText(""); setError(""); setNotice(""); }

  async function save(e: React.FormEvent) {
    e.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const payload = { ...draft, category: draft.category.trim(), business_type: draft.business_type.trim(),
        roles: rolesText.split(",").map((x) => x.trim()).filter(Boolean) };
      const result = await request(editingId ? "/api/v1/platform/industry-catalog/" + editingId : "/api/v1/platform/industry-catalog", {
        method: editingId ? "PATCH" : "POST", body: JSON.stringify(payload),
      });
      setNotice(editingId ? "Business type updated." : "Business type added.");
      reset(); setItems((prev) => editingId ? prev.map((x) => x.id === result.id ? result : x) : [...prev, result]);
    } catch (e) { setError(e instanceof Error ? e.message : "Save failed"); }
    finally { setSaving(false); }
  }

  async function disable(item: Entry) {
    if (!window.confirm("Disable “" + item.business_type + "”? Existing tenant selections will be retained.")) return;
    setError(""); setNotice("");
    try { await request("/api/v1/platform/industry-catalog/" + item.id, { method: "DELETE" });
      setItems((prev) => prev.map((x) => x.id === item.id ? { ...x, is_active: false } : x));
      setNotice("Business type disabled. Existing tenant configuration was not deleted.");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not disable entry"); }
  }

  return <main style={{ maxWidth: 1240, margin: "0 auto", padding: "28px 22px 60px", color: "#17213a" }}>
    <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "flex-start", marginBottom: 22 }}>
      <div><p style={{ margin: "0 0 8px", color: "#625ff0", fontSize: 11, fontWeight: 800, letterSpacing: ".12em" }}>SUPER ADMIN / CONFIGURATION</p>
        <h1 style={{ margin: 0, fontSize: 28, letterSpacing: "-.04em" }}>Industry catalogue</h1>
        <p style={{ margin: "8px 0 0", color: "#778298", fontSize: 13, maxWidth: 650 }}>Manage global industry categories, business subcategories, and suggested departments or job roles. Tenant custom settings remain separate.</p>
      </div>
      <a href="/platform" style={{ color: "#5b5cf0", fontWeight: 700, fontSize: 12, textDecoration: "none" }}>← Platform overview</a>
    </div>

    {error && <div role="alert" style={{ ...panel, borderColor: "#f2b8b8", color: "#a52a2a", marginBottom: 14, background: "#fffafa" }}>{error}</div>}
    {notice && <div role="status" style={{ ...panel, borderColor: "#bdebd6", color: "#16774d", marginBottom: 14, background: "#f7fffb" }}>{notice}</div>}

    <form onSubmit={save} style={{ ...panel, marginBottom: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", alignItems: "center", marginBottom: 18 }}>
        <h2 style={{ margin: 0, fontSize: 16 }}>{editingId ? "Edit business subcategory" : "Add a category / business type"}</h2>
        {editingId && <button type="button" onClick={reset} style={{ ...button, background: "#eef0f6", color: "#39445a" }}>Cancel edit</button>}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
        <div><label style={label}>Industry category *</label><input required minLength={2} maxLength={160} value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} placeholder="e.g. Healthcare & Wellness" style={input} /></div>
        <div><label style={label}>Business type / subcategory *</label><input required minLength={2} maxLength={200} value={draft.business_type} onChange={(e) => setDraft({ ...draft, business_type: e.target.value })} placeholder="e.g. Dental clinic" style={input} /></div>
        <div><label style={label}>Display order</label><input type="number" min={0} max={100000} value={draft.sort_order} onChange={(e) => setDraft({ ...draft, sort_order: Number(e.target.value) })} style={input} /></div>
      </div>
      <div style={{ marginTop: 14 }}><label style={label}>Suggested departments / roles (comma separated)</label><textarea rows={3} value={rolesText} onChange={(e) => setRolesText(e.target.value)} placeholder="Receptionist, Sales Manager, Technician…" style={{ ...input, resize: "vertical" }} /></div>
      <label style={{ display: "flex", alignItems: "center", gap: 8, color: "#4b5563", fontSize: 12, marginTop: 14 }}><input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} /> Active and available during onboarding</label>
      <div style={{ marginTop: 18, display: "flex", gap: 10, flexWrap: "wrap" }}><button disabled={saving} type="submit" style={{ ...button, opacity: saving ? .6 : 1 }}>{saving ? "Saving…" : editingId ? "Save changes" : "Add business type"}</button><button type="button" onClick={load} style={{ ...button, background: "#eef0f6", color: "#39445a" }}>Refresh</button></div>
    </form>

    <section style={panel}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
        <div><h2 style={{ margin: 0, fontSize: 16 }}>Catalogue entries <span style={{ color: "#7b879a", fontSize: 12, fontWeight: 500 }}>({visible.length})</span></h2><p style={{ margin: "5px 0 0", color: "#8a94a5", fontSize: 12 }}>Disable instead of deleting to preserve existing tenant selections.</p></div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search category, business type, role…" style={{ ...input, width: 260 }} /><label style={{ display: "flex", gap: 6, alignItems: "center", color: "#647087", fontSize: 12 }}><input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} /> Show inactive</label></div>
      </div>
      {loading ? <p style={{ color: "#7b879a", fontSize: 13 }}>Loading catalogue…</p> : visible.length === 0 ? <p style={{ color: "#7b879a", fontSize: 13 }}>No matching entries.</p> : <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, minWidth: 780 }}><thead><tr>{["Industry category", "Business type", "Suggested roles", "Status", "Actions"].map((x) => <th key={x} style={{ textAlign: "left", color: "#8792a4", fontSize: 10, textTransform: "uppercase", letterSpacing: ".07em", padding: "10px 9px", borderBottom: "1px solid #edf0f5" }}>{x}</th>)}</tr></thead>
          <tbody>{visible.map((item) => <tr key={item.id} style={{ borderBottom: "1px solid #f0f2f7", opacity: item.is_active ? 1 : .65 }}><td style={{ padding: "12px 9px", fontWeight: 700, minWidth: 180 }}>{item.category}</td><td style={{ padding: "12px 9px", minWidth: 190 }}>{item.business_type}</td><td style={{ padding: "12px 9px", color: "#69758b", maxWidth: 420 }}>{item.roles.slice(0, 5).join(", ")}{item.roles.length > 5 ? " +" + (item.roles.length - 5) + " more" : ""}</td><td style={{ padding: "12px 9px" }}><span style={{ borderRadius: 20, padding: "4px 8px", fontSize: 10, fontWeight: 800, background: item.is_active ? "#e9faf2" : "#f0f1f4", color: item.is_active ? "#1d9c68" : "#7d8796" }}>{item.is_active ? "ACTIVE" : "INACTIVE"}</span></td><td style={{ padding: "12px 9px", whiteSpace: "nowrap" }}><button type="button" onClick={() => edit(item)} style={{ ...button, padding: "7px 10px", background: "#eef0ff", color: "#5553d8", marginRight: 6 }}>Edit</button>{item.is_active && <button type="button" onClick={() => void disable(item)} style={{ ...button, padding: "7px 10px", background: "#fff0ef", color: "#a43e3e" }}>Disable</button>}</td></tr>)}</tbody>
        </table>
      </div>}
    </section>
  </main>;
}
