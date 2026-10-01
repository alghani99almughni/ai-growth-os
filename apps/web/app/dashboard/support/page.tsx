"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function TenantSupport() {
  const [tickets, setTickets] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [sending, setSending] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [tenantId, setTenantId] = useState("");
  const [form, setForm] = useState({ subject: "", body: "", category: "support", priority: "normal" });
  const [selected, setSelected] = useState<any>(null);
  const [replyText, setReplyText] = useState("");

  function headers() {
    return {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || ""),
    };
  }

  useEffect(() => {
    const raw = localStorage.getItem("ago_tenant");
    let t: any = null;
    try { t = raw ? JSON.parse(raw) : null; } catch {}
    if (!t?.id) { window.location.href = "/dashboard"; return; }
    setTenantId(t.id);
    void load(t.id);
  }, []);

  async function load(id: string) {
    setLoading(true);
    try {
      const r = await fetch(api() + "/api/v1/tenants/" + id + "/tickets", {
        headers: headers(),
        cache: "no-store",
      });
      if (r.status === 401) { window.location.href = "/login"; return; }
      const x = await r.json();
      setTickets(x.items || []);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    }
    setLoading(false);
  }

  async function submit() {
    if (!form.subject.trim()) { setStatus("Subject is required"); return; }
    setSending(true); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/tenants/" + tenantId + "/tickets", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(form),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Submit failed");
      setStatus("Ticket #" + x.id.slice(0, 8) + " submitted. Our team will respond within " + x.sla_hours + "h.");
      setForm({ subject: "", body: "", category: "support", priority: "normal" });
      setShowForm(false);
      void load(tenantId);
    } catch (e: any) {
      setStatus(e.message);
    }
    setSending(false);
  }

  async function reply() {
    if (!selected || !replyText.trim()) return;
    setSending(true); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/tenants/" + tenantId + "/tickets/" + selected.id + "/reply", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({ message: replyText.trim() }),
      });
      if (!r.ok) throw new Error("Reply failed");
      const updated = await r.json();
      setSelected(updated);
      setReplyText("");
      setStatus("Reply sent");
      void load(tenantId);
    } catch (e: any) {
      setStatus(e.message);
    }
    setSending(false);
  }

  function slaLabel(t: any) {
    if (t.status === "resolved" || t.status === "closed") return { bg: "#e9faf2", fg: "#1d9c68", label: "Resolved" };
    if (t.sla_breached) return { bg: "#fff1f1", fg: "#c74646", label: "We're on it" };
    const rem = t.sla_remaining_seconds || 0;
    const h = Math.floor(rem / 3600);
    const m = Math.floor((rem % 3600) / 60);
    return { bg: "#fff9e6", fg: "#c98c1a", label: "Response due in " + (h > 0 ? h + "h " + m + "m" : m + "m") };
  }

  if (!tenantId) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;

  return (
    <div>
      <div style={{ marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Support</h1>
          <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
            Raise a concern or check the status of an open ticket.
          </p>
        </div>
        <button onClick={() => setShowForm(!showForm)} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
          {showForm ? "Cancel" : "+ New ticket"}
        </button>
      </div>

      {showForm && (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24, marginBottom: 18 }}>
          <h2 style={{ margin: "0 0 16px", fontSize: 15, color: "#17213a" }}>Raise a new ticket</h2>
          <div style={{ display: "grid", gap: 14, maxWidth: 560 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
              Category
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} style={inputStyle}>
                <option value="support">Support</option>
                <option value="billing">Billing</option>
                <option value="contact">General enquiry</option>
                <option value="critical">Urgent / critical</option>
              </select>
            </label>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
              Priority
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} style={inputStyle}>
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </label>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
              Subject
              <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} placeholder="Short summary of the issue" style={inputStyle} />
            </label>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
              Details
              <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} rows={6} placeholder="What happened? When? Any error messages?" style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }} />
            </label>
            <button onClick={submit} disabled={sending} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "12px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: sending ? "wait" : "pointer", justifySelf: "start" }}>
              {sending ? "Submitting…" : "Submit ticket"}
            </button>
          </div>
        </div>
      )}

      {status && <p style={{ margin: "0 0 14px", fontSize: 12, color: "#1aa76c" }}>{status}</p>}
      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {selected ? (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, marginBottom: 16 }}>
            <div>
              <h2 style={{ margin: "0 0 4px", fontSize: 16, color: "#17213a" }}>{selected.subject}</h2>
              <p style={{ margin: 0, fontSize: 12, color: "#75839a" }}>
                {selected.category} · {selected.status.replace(/_/g, " ")} · created {new Date(selected.created_at).toLocaleString()}
              </p>
            </div>
            <button onClick={() => setSelected(null)} style={{ background: "transparent", border: 0, color: "#8490a4", cursor: "pointer", fontSize: 13 }}>← Back to list</button>
          </div>

          <div style={{ background: "#fafbfd", borderRadius: 10, padding: 16, fontSize: 13, lineHeight: 1.7, color: "#4b5563", whiteSpace: "pre-wrap", marginBottom: 16 }}>
            {selected.body || "(No messages yet)"}
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>Your reply</label>
            <textarea value={replyText} onChange={(e) => setReplyText(e.target.value)} rows={4} placeholder="Add more info or a follow-up…" style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }} />
          </div>
          <button onClick={reply} disabled={sending || !replyText.trim()} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: sending ? "wait" : "pointer" }}>
            {sending ? "Sending…" : "Send reply"}
          </button>
        </div>
      ) : loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>
      ) : tickets.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px dashed #dbe1ea", borderRadius: 14 }}>
          <h3 style={{ margin: "0 0 6px", color: "#17213a", fontSize: 15 }}>No tickets yet</h3>
          <p style={{ margin: 0, fontSize: 13 }}>Click "+ New ticket" if something isn't working.</p>
        </div>
      ) : (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
          {tickets.map((t) => {
            const sla = slaLabel(t);
            return (
              <button key={t.id} onClick={() => setSelected(t)} style={{ display: "block", width: "100%", textAlign: "left", padding: "16px 20px", borderBottom: "1px solid #f1f4f8", background: "transparent", border: 0, cursor: "pointer" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#17213a" }}>{t.subject}</div>
                    <div style={{ fontSize: 11, color: "#8b95a5", marginTop: 4 }}>
                      {t.category} · created {new Date(t.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ display: "inline-block", padding: "4px 10px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: "#edf2ff", color: "#566ce1" }}>
                      {t.status.replace(/_/g, " ")}
                    </span>
                    <span style={{ display: "inline-block", padding: "4px 10px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: sla.bg, color: sla.fg }}>
                      {sla.label}
                    </span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = { display: "block", width: "100%", marginTop: 6, padding: 10, borderRadius: 8, border: "1px solid #d7dce5", fontSize: 13, outline: "none", marginBottom: 14 };