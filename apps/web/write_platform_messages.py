"""Write the platform messages page."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "platform" / "messages" / "page.tsx"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = '''"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function MessagesPage() {
  const [items, setItems] = useState<any[]>([]);
  const [tenants, setTenants] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [showCompose, setShowCompose] = useState(false);
  const [form, setForm] = useState({ tenant_id: "", subject: "", body: "", send_email: true });
  const [sending, setSending] = useState(false);

  function headers() {
    return {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || ""),
    };
  }

  async function load() {
    setLoading(true);
    try {
      const [m, t] = await Promise.all([
        fetch(api() + "/api/v1/platform/messages", { headers: headers(), cache: "no-store" }).then(r => r.json()),
        fetch(api() + "/api/v1/platform/tenants", { headers: headers(), cache: "no-store" }).then(r => r.json()),
      ]);
      setItems(m.items || []);
      setTenants(t.items || []);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    }
    setLoading(false);
  }

  useEffect(() => { void load(); }, []);

  async function send() {
    if (!form.tenant_id || !form.subject.trim()) { setStatus("Pick a tenant and enter a subject"); return; }
    setSending(true); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/tenants/" + form.tenant_id + "/messages", {
        method: "POST", headers: headers(),
        body: JSON.stringify({ subject: form.subject, body: form.body, send_email: form.send_email }),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Send failed");
      setStatus("Message sent. Email status: " + (x.email_status || "—"));
      setForm({ tenant_id: "", subject: "", body: "", send_email: true });
      setShowCompose(false);
      void load();
    } catch (e: any) {
      setStatus(e.message);
    }
    setSending(false);
  }

  return (
    <div>
      <div style={{ marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Platform Messages</h1>
          <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
            Messages you have sent to tenants. They appear in the tenant dashboard bell.
          </p>
        </div>
        <button onClick={() => setShowCompose(!showCompose)} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
          {showCompose ? "Cancel" : "+ New message"}
        </button>
      </div>

      {showCompose && (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24, marginBottom: 18 }}>
          <h2 style={{ margin: "0 0 16px", fontSize: 15, color: "#17213a" }}>Compose message</h2>
          <div style={{ display: "grid", gap: 14, maxWidth: 560 }}>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
              To tenant
              <select value={form.tenant_id} onChange={(e) => setForm({ ...form, tenant_id: e.target.value })} style={inputStyle}>
                <option value="">— Select a tenant —</option>
                {tenants.map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
              Subject
              <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} placeholder="e.g. Important: WhatsApp configuration update" style={inputStyle} />
            </label>
            <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
              Message
              <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} rows={6} placeholder="Write the message…" style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }} />
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#4b5563" }}>
              <input type="checkbox" checked={form.send_email} onChange={(e) => setForm({ ...form, send_email: e.target.checked })} style={{ width: "auto", margin: 0 }} />
              Also send email to tenant owner
            </label>
            <button onClick={send} disabled={sending} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "12px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: sending ? "wait" : "pointer", justifySelf: "start" }}>
              {sending ? "Sending…" : "Send message"}
            </button>
          </div>
        </div>
      )}

      {status && <p style={{ margin: "0 0 14px", fontSize: 12, color: "#1aa76c" }}>{status}</p>}
      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px dashed #dbe1ea", borderRadius: 14 }}>
          <h3 style={{ margin: "0 0 6px", color: "#17213a", fontSize: 15 }}>No messages yet</h3>
          <p style={{ margin: 0, fontSize: 13 }}>Click "New message" to send your first one.</p>
        </div>
      ) : (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#fafbfd" }}>
              <tr>
                <th style={thStyle}>Subject</th>
                <th style={thStyle}>Tenant</th>
                <th style={thStyle}>Email</th>
                <th style={thStyle}>Read</th>
                <th style={thStyle}>Sent</th>
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr key={m.id} style={{ borderTop: "1px solid #f1f4f8" }}>
                  <td style={tdStyle}><strong style={{ color: "#17213a" }}>{m.subject}</strong><div style={{ color: "#8b95a5", fontSize: 11, marginTop: 4 }}>{m.body.slice(0, 80)}{m.body.length > 80 ? "…" : ""}</div></td>
                  <td style={tdStyle}>{m.tenant_id.slice(0, 12)}…</td>
                  <td style={tdStyle}>
                    <span style={{ display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: m.email_sent ? "#e9faf2" : "#f2f4f8", color: m.email_sent ? "#1d9c68" : "#6b7686" }}>
                      {m.email_status || "—"}
                    </span>
                  </td>
                  <td style={tdStyle}>{m.read_at ? "✓ " + new Date(m.read_at).toLocaleDateString() : "—"}</td>
                  <td style={tdStyle}>{m.created_at ? new Date(m.created_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = { display: "block", width: "100%", marginTop: 6, padding: 10, borderRadius: 8, border: "1px solid #d7dce5", fontSize: 13, outline: "none" };
const thStyle: React.CSSProperties = { textAlign: "left", padding: "12px 16px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5" };
const tdStyle: React.CSSProperties = { padding: "13px 16px", color: "#4b5563", verticalAlign: "top" };
'''

TARGET.write_text(CONTENT, encoding="utf-8")
print(f"File saved: {TARGET.stat().st_size} bytes")