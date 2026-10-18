"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const panel: React.CSSProperties = { background: "#fff", border: "1px solid #e5eaf2", borderRadius: 16, padding: 22, marginBottom: 18 };
const input: React.CSSProperties = { display: "block", width: "100%", padding: "11px 12px", marginTop: 6, border: "1px solid #d5dce8", borderRadius: 9, boxSizing: "border-box" };

export default function VisibilityWorkspace() {
  const [tenant, setTenant] = useState<any>(null);
  const [brand, setBrand] = useState<any>({ name: "", primary_domain: "", description: "", locale: "en" });
  const [competitors, setCompetitors] = useState<any[]>([]);
  const [queries, setQueries] = useState<any[]>([]);
  const [audits, setAudits] = useState<any[]>([]);
  const [selectedAudit, setSelectedAudit] = useState<any>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [auditBusy, setAuditBusy] = useState(false);
  const [competitor, setCompetitor] = useState({ name: "", domain: "", notes: "" });
  const [query, setQuery] = useState({ query_text: "", intent: "local", locale: "en", topic: "" });
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const token = () => typeof window === "undefined" ? "" : localStorage.getItem("ago_access_token") || "";
  const headers = () => ({ Authorization: "Bearer " + token(), "Content-Type": "application/json" });
  const endpoint = (id: string, suffix: string) => api() + "/api/v1/tenants/" + encodeURIComponent(id) + "/visibility/" + suffix;

  async function load(id: string) {
    const [b, c, q] = await Promise.all([
      fetch(endpoint(id, "brand"), { headers: headers(), cache: "no-store" }),
      fetch(endpoint(id, "competitors"), { headers: headers(), cache: "no-store" }),
      fetch(endpoint(id, "queries"), { headers: headers(), cache: "no-store" }),
    ]);
    if ([b, c, q].some(r => r.status === 401 || r.status === 403)) throw new Error("Your session does not have access to this business. Please sign in again.");
    if (![b, c, q].every(r => r.ok)) throw new Error("Visibility API is not available yet. Please check the backend deployment.");
    const [bd, cd, qd] = await Promise.all([b.json(), c.json(), q.json()]);
    const ar = await fetch(endpoint(id, "audits"), { headers: headers(), cache: "no-store" });
    const ad = ar.ok ? await ar.json() : { items: [] };
    setAudits(ad.items || []);
    if (bd.brand) setBrand(bd.brand);
    setCompetitors(cd.items || []);
    setQueries(qd.items || []);
  }

  useEffect(() => {
    try {
      const raw = localStorage.getItem("ago_tenant");
      const t = raw ? JSON.parse(raw) : null;
      if (!localStorage.getItem("ago_access_token") || !t?.id) { window.location.href = "/login"; return; }
      setTenant(t);
      load(t.id).catch(e => setStatus(e.message));
    } catch { setStatus("Could not load your business workspace."); }
  }, []);

  async function viewAudit(id: string) {
    if (!tenant) return;
    setDetailBusy(true);
    try {
      const r = await fetch(endpoint(tenant.id, "audits/" + encodeURIComponent(id)), { headers: headers(), cache: "no-store" });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Could not load audit details.");
      setSelectedAudit(d);
    } catch (e: any) { setStatus(e.message || "Could not load audit details."); }
    finally { setDetailBusy(false); }
  }

  async function runAudit() {
    if (!tenant) return;
    setAuditBusy(true); setStatus("");
    try {
      const r = await fetch(endpoint(tenant.id, "audits"), { method: "POST", headers: headers() });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Website audit failed.");
      setStatus("Website audit completed. " + (d.findings || []).length + " finding(s) recorded.");
      await load(tenant.id);
    } catch (e: any) { setStatus(e.message || "Website audit failed."); }
    finally { setAuditBusy(false); }
  }

  async function saveBrand(e: React.FormEvent) {
    e.preventDefault(); if (!tenant) return; setBusy(true); setStatus("");
    try {
      const r = await fetch(endpoint(tenant.id, "brand"), { method: "PUT", headers: headers(), body: JSON.stringify(brand) });
      const d = await r.json(); if (!r.ok) throw new Error(d.detail || "Could not save brand profile.");
      setBrand(d.brand); setStatus("Brand profile saved.");
    } catch (e: any) { setStatus(e.message || "Save failed."); } finally { setBusy(false); }
  }
  async function addCompetitor(e: React.FormEvent) {
    e.preventDefault(); if (!tenant) return; setBusy(true); setStatus("");
    try {
      const r = await fetch(endpoint(tenant.id, "competitors"), { method: "POST", headers: headers(), body: JSON.stringify(competitor) });
      const d = await r.json(); if (!r.ok) throw new Error(d.detail || "Could not add competitor.");
      setCompetitor({ name: "", domain: "", notes: "" }); await load(tenant.id); setStatus("Competitor added.");
    } catch (e: any) { setStatus(e.message || "Save failed."); } finally { setBusy(false); }
  }
  async function addQuery(e: React.FormEvent) {
    e.preventDefault(); if (!tenant) return; setBusy(true); setStatus("");
    try {
      const r = await fetch(endpoint(tenant.id, "queries"), { method: "POST", headers: headers(), body: JSON.stringify(query) });
      const d = await r.json(); if (!r.ok) throw new Error(d.detail || "Could not add query.");
      setQuery({ query_text: "", intent: "local", locale: "en", topic: "" }); await load(tenant.id); setStatus("Question added to your tracking library.");
    } catch (e: any) { setStatus(e.message || "Save failed."); } finally { setBusy(false); }
  }
  async function deleteCompetitor(id: string) {
    if (!tenant || !window.confirm("Remove this competitor?")) return;
    const r = await fetch(endpoint(tenant.id, "competitors/" + id), { method: "DELETE", headers: headers() });
    if (r.ok) { await load(tenant.id); setStatus("Competitor removed."); } else setStatus("Could not remove competitor.");
  }

  return <main style={{ maxWidth: 1180, margin: "0 auto", color: "#182337" }}>
    <header style={{ ...panel, background: "linear-gradient(120deg,#10243b,#214c59)", color: "white" }}>
      <p style={{ letterSpacing: 2, fontSize: 12, opacity: .8 }}>AI GROWTH OS · NEW WORKSPACE</p>
      <h1 style={{ fontSize: 34, margin: "8px 0" }}>AI Search Visibility</h1>
      <p style={{ maxWidth: 760, lineHeight: 1.6, opacity: .9 }}>Prepare your business to be discovered in search results and AI-generated answers. Configure your brand, competitors and the questions customers ask.</p>
      <span style={{ display: "inline-block", padding: "6px 10px", borderRadius: 20, background: "#ffffff20", fontSize: 12 }}>Foundation phase · Live AI checks not yet enabled</span>
    </header>
    {status && <div role="status" style={{ ...panel, borderColor: "#d4b46a", background: "#fffaf0" }}>{status}</div>}
    <section style={panel}><h2>1. Your brand</h2><p>Set the public website and basic business context used by future audits and visibility checks.</p>
      <form onSubmit={saveBrand} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))", gap: 14 }}>
        <label>Business / brand name<input required maxLength={180} style={input} value={brand.name || ""} onChange={e => setBrand({ ...brand, name: e.target.value })}/></label>
        <label>Website domain<input required placeholder="https://example.com" style={input} value={brand.primary_domain || ""} onChange={e => setBrand({ ...brand, primary_domain: e.target.value })}/></label>
        <label>Language / locale<input style={input} value={brand.locale || "en"} onChange={e => setBrand({ ...brand, locale: e.target.value })}/></label>
        <label style={{ gridColumn: "1 / -1" }}>Business description<textarea maxLength={4000} style={{ ...input, minHeight: 90 }} value={brand.description || ""} onChange={e => setBrand({ ...brand, description: e.target.value })}/></label>
        <div><button disabled={busy} style={{ padding: "11px 18px", border: 0, borderRadius: 9, background: "#176b63", color: "white", cursor: "pointer" }}>{busy ? "Saving…" : "Save brand profile"}</button></div>
      </form>
    </section>
    <section style={panel}><h2>2. Competitors</h2><p>Track businesses customers might compare with yours. Only public domains are accepted.</p>
      <form onSubmit={addCompetitor} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, alignItems: "end" }}>
        <label>Competitor name<input required style={input} value={competitor.name} onChange={e => setCompetitor({ ...competitor, name: e.target.value })}/></label>
        <label>Website domain<input required placeholder="competitor.com" style={input} value={competitor.domain} onChange={e => setCompetitor({ ...competitor, domain: e.target.value })}/></label>
        <label>Notes (optional)<input style={input} value={competitor.notes} onChange={e => setCompetitor({ ...competitor, notes: e.target.value })}/></label>
        <button disabled={busy} style={{ padding: 12, border: 0, borderRadius: 9, background: "#176b63", color: "white" }}>Add competitor</button>
      </form>
      {competitors.length === 0 ? <p style={{ color: "#69778a" }}>No competitors added yet.</p> : <div style={{ overflowX: "auto" }}><table style={{ width: "100%", textAlign: "left", borderCollapse: "collapse", marginTop: 14 }}><thead><tr><th style={{ padding: 10 }}>Name</th><th>Domain</th><th>Notes</th><th></th></tr></thead><tbody>{competitors.map(c => <tr key={c.id} style={{ borderTop: "1px solid #e8edf4" }}><td style={{ padding: 10 }}>{c.name}</td><td>{c.domain}</td><td>{c.notes}</td><td><button onClick={() => deleteCompetitor(c.id)}>Remove</button></td></tr>)}</tbody></table></div>}
    </section>
    <section style={panel}><h2>3. Questions customers ask</h2><p>Build a list of real questions to check later against supported AI/search providers.</p>
      <form onSubmit={addQuery} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, alignItems: "end" }}>
        <label style={{ gridColumn: "span 2" }}>Customer question<input required minLength={3} maxLength={500} placeholder="Who is the best [service] near [location]?" style={input} value={query.query_text} onChange={e => setQuery({ ...query, query_text: e.target.value })}/></label>
        <label>Intent<select style={input} value={query.intent} onChange={e => setQuery({ ...query, intent: e.target.value })}><option value="local">Local</option><option value="informational">Informational</option><option value="comparison">Comparison</option><option value="transactional">Transactional</option><option value="navigational">Navigational</option></select></label>
        <label>Topic<input style={input} value={query.topic} onChange={e => setQuery({ ...query, topic: e.target.value })}/></label>
        <button disabled={busy} style={{ padding: 12, border: 0, borderRadius: 9, background: "#176b63", color: "white" }}>Add question</button>
      </form>
      <div style={{ display: "grid", gap: 8, marginTop: 16 }}>{queries.map(q => <article key={q.id} style={{ padding: 12, border: "1px solid #e8edf4", borderRadius: 10 }}><strong>{q.query_text}</strong><div style={{ color: "#69778a", fontSize: 13, marginTop: 5 }}>{q.intent} · {q.locale}{q.topic ? " · " + q.topic : ""}</div></article>)}</div>
    </section>
    <section style={panel}><h2>4. Website audit</h2><p>Run a bounded check of the saved public homepage for basic SEO and discoverability issues. This is a single-page audit, not a guarantee of search ranking.</p><button onClick={runAudit} disabled={auditBusy || busy || !brand.primary_domain} style={{ padding: "12px 18px", border: 0, borderRadius: 9, background: "#176b63", color: "white", cursor: "pointer" }}>{auditBusy ? "Checking website…" : "Run homepage audit"}</button>
      {audits.length > 0 && <div style={{ marginTop: 16, overflowX: "auto" }}><h3>Audit history</h3><table style={{ width: "100%", textAlign: "left", borderCollapse: "collapse" }}><thead><tr><th style={{ padding: 10 }}>Date</th><th>Website</th><th>Status</th><th>HTTP</th><th>Findings</th></tr></thead><tbody>{audits.map(a => <tr key={a.id} style={{ borderTop: "1px solid #e8edf4" }}><td style={{ padding: 10 }}>{a.created_at ? new Date(a.created_at).toLocaleString() : "—"}</td><td>{a.target_url}</td><td>{a.status}</td><td>{a.http_status ?? "—"}</td><td>{a.summary?.finding_count ?? "—"} <button onClick={() => viewAudit(a.id)} style={{ marginLeft: 8 }}>View findings</button></td></tr>)}</tbody></table></div>}
      {detailBusy && <p>Loading audit findings…</p>}
      {selectedAudit && <div style={{ marginTop: 18, padding: 16, border: "1px solid #dbe4ee", borderRadius: 12 }}><h3>Findings for {selectedAudit.target_url}</h3><p>{selectedAudit.pages_checked} page checked · HTTP {selectedAudit.http_status ?? "unknown"} · {selectedAudit.status}</p><button onClick={() => setSelectedAudit(null)}>Close findings</button>{(selectedAudit.findings || []).map((finding: any, i: number) => <article key={i} style={{ marginTop: 10, padding: 12, border: "1px solid #e8edf4", borderRadius: 9 }}><strong>{finding.title}</strong><div style={{ fontSize: 12, color: "#69778a", margin: "4px 0" }}>{finding.category} · {finding.severity}</div><p>{finding.recommendation}</p>{finding.evidence && <small>Evidence: {finding.evidence}</small>}</article>)}</div>}
    </section>
    <section style={{ ...panel, background: "#f8fafc" }}><h2>Next development milestone</h2><div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12 }}><div><strong>Deeper website audits</strong><p>Sitemap, internal links and content coverage with strict crawl limits.</p></div><div><strong>AI answer observations</strong><p>Provider-backed checks with timestamps, cited URLs and method labels.</p></div><div><strong>Reports and trends</strong><p>Historical changes and recommendations tied to actual evidence.</p></div></div><small>AI rankings and citations will only be reported after real provider checks complete.</small></section>
  </main>;
}
