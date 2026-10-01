"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type EmailAccount = {
  id: string;
  label: string;
  provider: string;
  email_address: string;
  role: string;
  is_active: boolean;
  auto_reply_enabled: boolean;
  last_checked_at: string | null;
  last_error: string | null;
  created_at: string | null;
};

type EmailLogRow = {
  id: string;
  from_address: string;
  to_address: string;
  subject: string;
  outcome: string;
  reply_text: string | null;
  error: string | null;
  ticket_id: string | null;
  created_at: string | null;
};

export default function EmailPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);
  const [logs, setLogs] = useState<EmailLogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState("");

  const [form, setForm] = useState({
    label: "Primary mailbox",
    provider: "gmail",
    email_address: "",
    role: "support",
    imap_host: "",
    imap_port: 993,
    imap_user: "",
    imap_password: "",
    smtp_host: "",
    smtp_port: 587,
    smtp_user: "",
    smtp_password: "",
  });

  const authHeaders = () => ({
    "Content-Type": "application/json",
    Authorization: "Bearer " + token,
  });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [a, l] = await Promise.all([
        jget(`/api/v1/tenants/${tenantId}/email-accounts`),
        jget(`/api/v1/tenants/${tenantId}/email-log?limit=50`).catch(() => ({ items: [] })),
      ]);
      setAccounts(a.items || []);
      setLogs(l.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load email accounts");
    }
    setLoading(false);
  }

    useEffect(() => {
    if (!tenantId) return;
    void loadAll();
    const iv = setInterval(() => { void loadAll(); }, 30000);
    return () => clearInterval(iv);
  }, [tenantId]);

  function updateField(k: string, v: any) {
    setForm((prev) => ({ ...prev, [k]: v }));
  }

  async function submit() {
    setSaving(true);
    setStatus("");
    try {
      const payload: any = { ...form };
      if (form.provider === "gmail" || form.provider === "outlook") {
        payload.imap_host = null;
        payload.imap_port = null;
        payload.smtp_host = null;
        payload.smtp_port = null;
      }
      const r = await fetch(api() + `/api/v1/tenants/${tenantId}/email-accounts`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify(payload),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Could not create account");
      setStatus("Mailbox connected: " + x.email_address);
      setShowForm(false);
      setForm({
        label: "Primary mailbox",
        provider: "gmail",
        email_address: "",
        role: "support",
        imap_host: "",
        imap_port: 993,
        imap_user: "",
        imap_password: "",
        smtp_host: "",
        smtp_port: 587,
        smtp_user: "",
        smtp_password: "",
      });
      await loadAll();
    } catch (e: any) {
      setStatus(e.message);
    }
    setSaving(false);
  }

  async function testAccount(id: string) {
    setTestingId(id);
    setStatus("");
    try {
      const r = await fetch(api() + `/api/v1/tenants/${tenantId}/email-accounts/${id}/test`, {
        method: "POST",
        headers: authHeaders(),
      });
      const x = await r.json();
      setStatus(x.ok ? "IMAP connection OK" : "IMAP failed: " + (x.error || "unknown"));
    } catch (e: any) {
      setStatus(e.message);
    }
    setTestingId("");
  }

  async function toggleActive(id: string, next: boolean) {
    try {
      await fetch(api() + `/api/v1/tenants/${tenantId}/email-accounts/${id}`, {
        method: "PATCH",
        headers: authHeaders(),
        body: JSON.stringify({ is_active: next }),
      });
      await loadAll();
    } catch (e: any) {
      setStatus(e.message);
    }
  }

  async function removeAccount(id: string, label: string) {
    if (!confirm(`Delete mailbox "${label}"?`)) return;
    try {
      await fetch(api() + `/api/v1/tenants/${tenantId}/email-accounts/${id}`, {
        method: "DELETE",
        headers: authHeaders(),
      });
      setStatus("Mailbox removed");
      await loadAll();
    } catch (e: any) {
      setStatus(e.message);
    }
  }

  return (
    <section className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0 }}>📧 Business mailboxes</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            {accounts.length} mailbox{accounts.length === 1 ? "" : "es"} configured.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-ghost" onClick={loadAll} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
          <button className="btn-primary" onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "+ Connect mailbox"}
          </button>
        </div>
      </div>

      {error && <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>}
      {status && <p style={{ color: "#1aa76c", marginTop: 12, fontSize: 12 }}>{status}</p>}

      {showForm && (
        <div style={{ marginTop: 20, padding: 16, background: "#f9fafc", border: "1px solid #e8ecf3", borderRadius: 12 }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>Connect a mailbox</h3>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <label>
              Provider
              <select
                value={form.provider}
                onChange={(e) => updateField("provider", e.target.value)}
                style={inputStyle}
              >
                <option value="gmail">Gmail (App Password)</option>
                <option value="outlook">Outlook / Microsoft 365</option>
                <option value="custom">Custom SMTP / IMAP</option>
              </select>
            </label>

            <label>
              Role
              <select
                value={form.role}
                onChange={(e) => updateField("role", e.target.value)}
                style={inputStyle}
              >
                <option value="support">support@ (auto-creates tickets)</option>
                <option value="contact">contact@ (auto-reply only)</option>
                <option value="billing">billing@ (auto-reply only)</option>
                <option value="general">general</option>
              </select>
            </label>

            <label style={{ gridColumn: "1 / -1" }}>
              Label
              <input value={form.label} onChange={(e) => updateField("label", e.target.value)} style={inputStyle} />
            </label>

            <label style={{ gridColumn: "1 / -1" }}>
              Email address
              <input
                value={form.email_address}
                onChange={(e) => updateField("email_address", e.target.value)}
                placeholder="support@yourdomain.com"
                style={inputStyle}
              />
            </label>

            {form.provider === "custom" && (
              <>
                <label>
                  IMAP host
                  <input value={form.imap_host} onChange={(e) => updateField("imap_host", e.target.value)} placeholder="imap.yourhost.com" style={inputStyle} />
                </label>
                <label>
                  IMAP port
                  <input type="number" value={form.imap_port} onChange={(e) => updateField("imap_port", Number(e.target.value))} style={inputStyle} />
                </label>
                <label>
                  SMTP host
                  <input value={form.smtp_host} onChange={(e) => updateField("smtp_host", e.target.value)} placeholder="smtp.yourhost.com" style={inputStyle} />
                </label>
                <label>
                  SMTP port
                  <input type="number" value={form.smtp_port} onChange={(e) => updateField("smtp_port", Number(e.target.value))} style={inputStyle} />
                </label>
              </>
            )}

            <label>
              IMAP/SMTP user
              <input value={form.imap_user} onChange={(e) => updateField("imap_user", e.target.value)} placeholder="usually the email address" style={inputStyle} />
            </label>
            <label>
              Password / App password
              <input
                type="password"
                value={form.imap_password}
                onChange={(e) => updateField("imap_password", e.target.value)}
                style={inputStyle}
              />
            </label>
          </div>

          <button
            className="btn-primary"
            onClick={submit}
            disabled={saving || !form.email_address || !form.imap_password}
            style={{ marginTop: 14, padding: "11px 20px" }}
          >
            {saving ? "Connecting…" : "Connect mailbox"}
          </button>
        </div>
      )}

      {/* Accounts list */}
      <div style={{ marginTop: 24 }}>
        {accounts.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No mailboxes connected</h3>
            <p>Connect contact@, support@, or billing@ to let AI auto-reply to incoming mail.</p>
          </div>
        )}

        {accounts.map((a) => (
          <article
            key={a.id}
            className="card"
            style={{ marginBottom: 10, padding: 14, background: "#fff" }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <strong style={{ fontSize: 14 }}>{a.email_address}</strong>
                  <span className="badge badge-blue">{a.provider}</span>
                  <span className="badge badge-purple">{a.role}</span>
                  <span className={"badge " + (a.is_active ? "badge-blue" : "badge-grey")}>
                    {a.is_active ? "active" : "paused"}
                  </span>
                </div>
                <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                  {a.label} · last checked {a.last_checked_at ? new Date(a.last_checked_at).toLocaleString() : "never"}
                </p>
                {a.last_error && (
                  <p style={{ margin: "4px 0 0", color: "#c74646", fontSize: 12 }}>
                    {a.last_error}
                  </p>
                )}
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button className="btn-ghost" onClick={() => testAccount(a.id)} disabled={testingId === a.id}>
                  {testingId === a.id ? "Testing…" : "Test"}
                </button>
                <button className="btn-ghost" onClick={() => toggleActive(a.id, !a.is_active)}>
                  {a.is_active ? "Pause" : "Resume"}
                </button>
                <button
                  className="btn-ghost"
                  style={{ color: "#c74646", borderColor: "#f0c6c6" }}
                  onClick={() => removeAccount(a.id, a.email_address)}
                >
                  Delete
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* Email activity log */}
      <div style={{ marginTop: 28, paddingTop: 20, borderTop: "1px solid #eef1f5" }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>Recent auto-replies</h3>
        {logs.length === 0 ? (
          <p style={{ color: "#75839a", fontSize: 13 }}>
            No incoming emails processed yet. Once the poller picks up mail, activity will appear here.
          </p>
        ) : (
          <div>
            {logs.map((l) => (
              <div
                key={l.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "8px 0",
                  fontSize: 12.5,
                  borderBottom: "1px solid #f1f4f8",
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <strong style={{ color: "#17213a" }}>{l.subject || "(no subject)"}</strong>
                  <span style={{ color: "#75839a" }}> from {l.from_address}</span>
                </div>
                <div style={{ display: "flex", gap: 8, color: "#75839a", flexShrink: 0 }}>
                  <span className={"badge " + (l.outcome === "replied" ? "badge-blue" : l.outcome === "ticket_created" ? "badge-purple" : l.outcome === "failed" ? "badge-grey" : "badge-grey")}>
                    {l.outcome}
                  </span>
                  <span>{l.created_at ? new Date(l.created_at.endsWith("Z") ? l.created_at : l.created_at + "Z").toLocaleTimeString() : ""}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 6,
  padding: 10,
  borderRadius: 8,
  border: "1px solid #d7dce5",
  fontSize: 13,
  outline: "none",
};