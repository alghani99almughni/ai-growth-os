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

type ThreadSummary = {
  thread_id: string;
  subject: string;
  from_address: string;
  to_address: string;
  last_at: string;
  message_count: number;
  unread: number;
  has_ticket: boolean;
};

type ThreadMessage = {
  id: string;
  message_id: string;
  from_address: string;
  to_address: string;
  subject: string;
  body: string;
  reply_text: string | null;
  outcome: string;
  in_reply_to: string | null;
  references_header: string | null;
  created_at: string;
};

type ThreadDetail = {
  thread_id: string;
  subject: string;
  from_address: string;
  to_address: string;
  last_at: string;
  message_count: number;
  unread: number;
  has_ticket: boolean;
  messages: ThreadMessage[];
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
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [selected, setSelected] = useState<ThreadDetail | null>(null);
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [threadsLoading, setThreadsLoading] = useState(false);
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

  async function loadThreads() {
    setThreadsLoading(true);
    try {
      const x = await jget(`/api/v1/tenants/${tenantId}/email-threads?limit=100`);
      setThreads(x.items || []);
    } catch (e: any) {
      setStatus(e.message || "Could not load conversations");
    }
    setThreadsLoading(false);
  }

  async function openThread(threadId: string) {
    setStatus("");
    try {
      const x = await jget(`/api/v1/tenants/${tenantId}/email-threads/${threadId}`);
      setSelected(x);
      setReplyText("");
    } catch (e: any) {
      setStatus(e.message || "Could not load thread");
    }
  }

  async function sendReply() {
    if (!selected || !replyText.trim()) return;
    setSending(true);
    setStatus("");
    try {
      const r = await fetch(api() + `/api/v1/tenants/${tenantId}/email-threads/${selected.thread_id}/reply`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ body: replyText.trim() }),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Reply failed");
      setStatus("Reply sent");
      setReplyText("");
      await openThread(selected.thread_id);
      await loadThreads();
    } catch (e: any) {
      setStatus(e.message);
    }
    setSending(false);
  }

  useEffect(() => {
    if (!tenantId) return;
    void loadAll();
    void loadThreads();
    const iv = setInterval(() => { void loadThreads(); }, 30000);
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
      setStatus(x.ok ? "IMAP + SMTP connection OK" : "Connection failed: " + (x.error || JSON.stringify(x)));
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

  function fmtTime(iso: string | null | undefined) {
    if (!iso) return "";
    const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
    return d.toLocaleString();
  }

  return (
    <section className="card">
      {/* ── Mailbox config header ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0 }}>📫 Business mailboxes</h2>
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
              <select value={form.provider} onChange={(e) => updateField("provider", e.target.value)} style={inputStyle}>
                <option value="gmail">Gmail (App Password)</option>
                <option value="outlook">Outlook / Microsoft 365</option>
                <option value="custom">Custom SMTP / IMAP</option>
              </select>
            </label>
            <label>
              Role
              <select value={form.role} onChange={(e) => updateField("role", e.target.value)} style={inputStyle}>
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
              <input value={form.email_address} onChange={(e) => updateField("email_address", e.target.value)} placeholder="support@yourdomain.com" style={inputStyle} />
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
              <input type="password" value={form.imap_password} onChange={(e) => updateField("imap_password", e.target.value)} style={inputStyle} />
            </label>
          </div>
          <button className="btn-primary" onClick={submit} disabled={saving || !form.email_address || !form.imap_password} style={{ marginTop: 14, padding: "11px 20px" }}>
            {saving ? "Connecting…" : "Connect mailbox"}
          </button>
        </div>
      )}

      {/* ── Accounts list ── */}
      <div style={{ marginTop: 24 }}>
        {accounts.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No mailboxes connected</h3>
            <p>Connect contact@, support@, or billing@ to let AI auto-reply and view conversations here.</p>
          </div>
        )}
        {accounts.map((a) => (
          <article key={a.id} className="card" style={{ marginBottom: 10, padding: 14, background: "#fff" }}>
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
                  {a.label} · last checked {fmtTime(a.last_checked_at) || "never"}
                </p>
                {a.last_error && <p style={{ margin: "4px 0 0", color: "#c74646", fontSize: 12 }}>{a.last_error}</p>}
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button className="btn-ghost" onClick={() => testAccount(a.id)} disabled={testingId === a.id}>
                  {testingId === a.id ? "Testing…" : "Test"}
                </button>
                <button className="btn-ghost" onClick={() => toggleActive(a.id, !a.is_active)}>
                  {a.is_active ? "Pause" : "Resume"}
                </button>
                <button className="btn-ghost" style={{ color: "#c74646", borderColor: "#f0c6c6" }} onClick={() => removeAccount(a.id, a.email_address)}>
                  Delete
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* ── Conversations (3-panel inbox) ── */}
      <div style={{ marginTop: 32, paddingTop: 20, borderTop: "1px solid #eef1f5" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 12 }}>
          <h3 style={{ margin: 0, fontSize: 15 }}>Conversations</h3>
          <button className="btn-ghost" onClick={loadThreads} disabled={threadsLoading}>
            {threadsLoading ? "Loading…" : "Refresh"}
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 12, minHeight: 400 }}>
          {/* Left: thread list */}
          <div style={{ background: "#fafbfc", border: "1px solid #eef1f5", borderRadius: 10, overflow: "hidden" }}>
            {threads.length === 0 ? (
              <p style={{ padding: 16, color: "#98a2b4", fontSize: 12, margin: 0 }}>
                No conversations yet. Once the poller picks up incoming mail, threads appear here.
              </p>
            ) : (
              threads.map((t) => (
                <button
                  key={t.thread_id}
                  onClick={() => openThread(t.thread_id)}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "10px 12px",
                    border: 0,
                    borderBottom: "1px solid #eef1f5",
                    background: selected?.thread_id === t.thread_id ? "#eaf2ff" : "transparent",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "baseline" }}>
                    <strong style={{ fontSize: 12.5, color: "#17213a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t.from_address}
                    </strong>
                    <span style={{ fontSize: 10.5, color: "#98a2b4", flexShrink: 0 }}>
                      {fmtTime(t.last_at).split(",")[0]}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "#4b5563", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {t.subject || "(no subject)"}
                  </div>
                  <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                    {t.message_count > 1 && (
                      <span style={{ fontSize: 10, color: "#75839a" }}>{t.message_count} msgs</span>
                    )}
                    {t.has_ticket && (
                      <span className="badge badge-purple" style={{ fontSize: 9.5 }}>ticket</span>
                    )}
                  </div>
                </button>
              ))
            )}
          </div>

          {/* Right: thread view */}
          <div style={{ background: "#fff", border: "1px solid #eef1f5", borderRadius: 10, padding: 16, display: "flex", flexDirection: "column" }}>
            {!selected ? (
              <p style={{ color: "#98a2b4", fontSize: 13, margin: "auto" }}>Select a conversation to view the thread.</p>
            ) : (
              <>
                <div style={{ marginBottom: 12, paddingBottom: 10, borderBottom: "1px solid #eef1f5" }}>
                  <strong style={{ fontSize: 14, color: "#17213a" }}>{selected.subject || "(no subject)"}</strong>
                  <div style={{ fontSize: 12, color: "#75839a", marginTop: 4 }}>
                    {selected.message_count} message{selected.message_count === 1 ? "" : "s"} · last {fmtTime(selected.last_at)}
                  </div>
                </div>

                <div style={{ flex: 1, overflowY: "auto", maxHeight: 340, paddingRight: 6 }}>
                  {selected.messages.map((m) => (
                    <div
                      key={m.id}
                      style={{
                        marginBottom: 12,
                        padding: 12,
                        borderRadius: 10,
                        background: m.reply_text ? "#f5f8ff" : "#fafbfc",
                        border: "1px solid #eef1f5",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 6 }}>
                        <strong style={{ fontSize: 12, color: "#17213a" }}>{m.from_address}</strong>
                        <span style={{ fontSize: 11, color: "#98a2b4" }}>{fmtTime(m.created_at)}</span>
                      </div>
                      {m.body && (
                        <pre style={{ margin: 0, fontFamily: "inherit", fontSize: 12.5, color: "#4b5563", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                          {m.body}
                        </pre>
                      )}
                      {m.reply_text && (
                        <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px dashed #d7dce5" }}>
                          <div style={{ fontSize: 11, color: "#75839a", marginBottom: 4 }}>↳ Our reply</div>
                          <pre style={{ margin: 0, fontFamily: "inherit", fontSize: 12.5, color: "#17213a", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                            {m.reply_text}
                          </pre>
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #eef1f5" }}>
                  <textarea
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    placeholder="Type your reply…"
                    rows={3}
                    style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical", marginTop: 0 }}
                  />
                  <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                    <button
                      className="btn-primary"
                      onClick={sendReply}
                      disabled={sending || !replyText.trim()}
                      style={{ padding: "10px 18px" }}
                    >
                      {sending ? "Sending…" : "Send reply"}
                    </button>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Recent auto-replies ── */}
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
                  <span className={"badge " + (l.outcome === "replied" ? "badge-blue" : l.outcome === "ticket_created" ? "badge-purple" : "badge-grey")}>
                    {l.outcome}
                  </span>
                  <span>{fmtTime(l.created_at)}</span>
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