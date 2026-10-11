"use client";
import { useEffect, useState } from "react";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type Account = { id: string; label: string; provider: string; email_address: string; role: string; is_active: boolean; auto_reply_enabled: boolean; last_checked_at: string | null; last_error: string | null };
type Row = { tenant_id: string; tenant_name: string; tenant_slug: string; industry: string; status: string; account_count: number; active_count: number; auto_reply_count: number; accounts: Account[]; activity_24h: Record<string, number> };
type Totals = { tenants: number; tenants_with_email: number; total_accounts: number; total_active: number; total_errors: number };

export default function PlatformEmailPage() {
  const [data, setData] = useState<{ totals: Totals; items: Row[] } | null>(null);
  const [open, setOpen] = useState<string>("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [configureFor, setConfigureFor] = useState<Row | null>(null);
  const [sendFor, setSendFor] = useState<Row | null>(null);
  const [statusMsg, setStatusMsg] = useState("");

  const token = () => (typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : "");

  async function load() {
    setLoading(true); setErr("");
    try {
      const r = await fetch(API + "/api/v1/platform/email/overview", { headers: { Authorization: "Bearer " + token() }, cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      setData(await r.json());
    } catch (e: any) { setErr(String(e?.message || "Load failed")); }
    finally { setLoading(false); }
  }

  useEffect(() => { void load(); }, []);

  if (loading) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  if (err) return <div style={{ padding: 40, color: "#b00" }}>{err}</div>;
  if (!data) return null;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Email across all tenants</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Connect a mailbox or send an email on behalf of any tenant.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 24 }}>
        <Kpi label="Tenants" value={data.totals.tenants} />
        <Kpi label="With email" value={data.totals.tenants_with_email} />
        <Kpi label="Mailboxes" value={data.totals.total_accounts} />
        <Kpi label="Active" value={data.totals.total_active} />
        <Kpi label="Errors" value={data.totals.total_errors} accent={data.totals.total_errors > 0 ? "#b00" : undefined} />
      </div>

      {statusMsg && <p style={{ color: "#1aa76c", fontSize: 13, marginBottom: 10 }}>{statusMsg}</p>}

      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead style={{ background: "#fafbfd" }}>
            <tr>
              <th style={th}>Tenant</th>
              <th style={th}>Mailboxes</th>
              <th style={th}>Auto-reply</th>
              <th style={th}>24h activity</th>
              <th style={th}>Errors</th>
              <th style={th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => {
              const errors = r.accounts.filter((a) => a.last_error).length;
              const replied = r.activity_24h["replied"] || 0;
              const tickets = r.activity_24h["ticket_created"] || 0;
              const failed = r.activity_24h["failed"] || 0;
              const isOpen = open === r.tenant_id;
              return (
                <>
                  <tr key={r.tenant_id} style={{ borderTop: "1px solid #f1f4f8" }}>
                    <td style={td}>
                      <strong style={{ color: "#17213a" }}>{r.tenant_name}</strong>
                      <div style={{ color: "#8b95a5", fontSize: 11 }}>/{r.tenant_slug} · {r.industry}</div>
                    </td>
                    <td style={td}>{r.account_count}</td>
                    <td style={td}>{r.auto_reply_count}</td>
                    <td style={td}>
                      {replied > 0 && <span style={chip("#e9faf2", "#1d9c68")}>{replied} replied</span>}
                      {tickets > 0 && <span style={chip("#f1ebff", "#6b4fbb")}>{tickets} tickets</span>}
                      {failed > 0 && <span style={chip("#fff1f1", "#c74646")}>{failed} failed</span>}
                      {replied + tickets + failed === 0 && <span style={{ color: "#98a2b4" }}>—</span>}
                    </td>
                    <td style={td}>{errors > 0 ? <span style={{ color: "#c74646" }}>{errors}</span> : <span style={{ color: "#98a2b4" }}>—</span>}</td>
                    <td style={td}>
                      <button onClick={() => setConfigureFor(r)} style={btn}>Add mailbox</button>
                      <button onClick={() => setSendFor(r)} style={btn} disabled={r.active_count === 0}>Send</button>
                      {r.account_count > 0 && (
                        <button onClick={() => setOpen(isOpen ? "" : r.tenant_id)} style={btn}>
                          {isOpen ? "Hide" : "View"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={6} style={{ background: "#fafbfd", padding: 0 }}>
                        <div style={{ padding: 16 }}>
                          {r.accounts.map((a) => (
                            <div key={a.id} style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 10, padding: 14, marginBottom: 8 }}>
                              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                                <strong style={{ color: "#17213a" }}>{a.email_address}</strong>
                                <span style={chip("#eaf0ff", "#4d6df3")}>{a.provider}</span>
                                <span style={chip("#f1ebff", "#6b4fbb")}>{a.role}</span>
                                <span style={chip(a.is_active ? "#e9faf2" : "#f2f4f8", a.is_active ? "#1d9c68" : "#6b7686")}>{a.is_active ? "active" : "paused"}</span>
                              </div>
                              <div style={{ fontSize: 12, color: "#75839a" }}>{a.label} · last checked {a.last_checked_at ? new Date(a.last_checked_at).toLocaleString() : "never"}</div>
                              {a.last_error && <div style={{ fontSize: 12, color: "#c74646", marginTop: 4 }}>{a.last_error}</div>}
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>

      {configureFor && <ConfigureModal row={configureFor} onClose={() => setConfigureFor(null)} onSaved={async () => { setConfigureFor(null); setStatusMsg("Mailbox added."); await load(); }} />}
      {sendFor && <SendModal row={sendFor} onClose={() => setSendFor(null)} />}
    </div>
  );
}

function ConfigureModal({ row, onClose, onSaved }: { row: Row; onClose: () => void; onSaved: () => void }) {
  const [provider, setProvider] = useState<"gmail" | "outlook" | "custom">("gmail");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("support");
  const [label, setLabel] = useState("Primary mailbox");
  const [imapHost, setImapHost] = useState("");
  const [imapPort, setImapPort] = useState(993);
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState(587);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setBusy(true); setErr("");
    try {
      const body: any = { label, provider, email_address: email, role, imap_password: password, smtp_password: password };
      if (provider === "custom") Object.assign(body, { imap_host: imapHost, imap_port: imapPort, smtp_host: smtpHost, smtp_port: smtpPort });
      const r = await fetch(`${API}/api/v1/platform/tenants/${row.tenant_id}/email/configure`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + (typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : "") },
        body: JSON.stringify(body),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x.detail || "Configure failed");
      onSaved();
    } catch (e: any) { setErr(String(e?.message || "Failed")); }
    finally { setBusy(false); }
  };

  return (
    <Modal title={`Add mailbox · ${row.tenant_name}`} onClose={onClose}>
      <label style={lbl}>Provider
        <select value={provider} onChange={(e) => setProvider(e.target.value as any)} style={inp}>
          <option value="gmail">Gmail (App password)</option>
          <option value="outlook">Outlook / Microsoft 365</option>
          <option value="custom">Custom SMTP / IMAP</option>
        </select>
      </label>
      <label style={lbl}>Role
        <select value={role} onChange={(e) => setRole(e.target.value)} style={inp}>
          <option value="support">support@ (auto-creates tickets)</option>
          <option value="contact">contact@ (auto-reply only)</option>
          <option value="billing">billing@ (auto-reply only)</option>
          <option value="general">general</option>
        </select>
      </label>
      <label style={lbl}>Label<input value={label} onChange={(e) => setLabel(e.target.value)} style={inp} /></label>
      <label style={lbl}>Email address<input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="support@yourdomain.com" style={inp} /></label>
      {provider === "custom" && (
        <>
          <label style={lbl}>IMAP host<input value={imapHost} onChange={(e) => setImapHost(e.target.value)} style={inp} /></label>
          <label style={lbl}>IMAP port<input type="number" value={imapPort} onChange={(e) => setImapPort(Number(e.target.value))} style={inp} /></label>
          <label style={lbl}>SMTP host<input value={smtpHost} onChange={(e) => setSmtpHost(e.target.value)} style={inp} /></label>
          <label style={lbl}>SMTP port<input type="number" value={smtpPort} onChange={(e) => setSmtpPort(Number(e.target.value))} style={inp} /></label>
        </>
      )}
      <label style={lbl}>App password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={inp} /></label>
      {err && <p style={{ color: "#b00", fontSize: 12 }}>{err}</p>}
      <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
        <button onClick={submit} disabled={busy || !email || !password} style={{ ...btn, background: "#1a5c43", color: "#fff", border: 0, padding: "10px 18px" }}>
          {busy ? "Connecting…" : "Add mailbox"}
        </button>
        <button onClick={onClose} style={btn}>Cancel</button>
      </div>
    </Modal>
  );
}

function SendModal({ row, onClose }: { row: Row; onClose: () => void }) {
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const submit = async () => {
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`${API}/api/v1/platform/tenants/${row.tenant_id}/email/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + (typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : "") },
        body: JSON.stringify({ to, subject, body }),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x.detail || "Send failed");
      setMsg("Sent from " + (x.from || "configured mailbox"));
      setTo(""); setSubject(""); setBody("");
    } catch (e: any) { setMsg(String(e?.message || "Failed")); }
    finally { setBusy(false); }
  };

  return (
    <Modal title={`Send email · ${row.tenant_name}`} onClose={onClose}>
      <p style={{ marginTop: 0, fontSize: 12, color: "#75839a" }}>Sends from the tenant&apos;s most recently added active mailbox.</p>
      <label style={lbl}>To<input value={to} onChange={(e) => setTo(e.target.value)} style={inp} /></label>
      <label style={lbl}>Subject<input value={subject} onChange={(e) => setSubject(e.target.value)} style={inp} /></label>
      <label style={lbl}>Body<textarea value={body} onChange={(e) => setBody(e.target.value)} rows={6} style={{ ...inp, fontFamily: "inherit" }} /></label>
      {msg && <p style={{ color: msg.startsWith("Sent") ? "#1aa76c" : "#b00", fontSize: 12 }}>{msg}</p>}
      <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
        <button onClick={submit} disabled={busy || !to || !subject || !body} style={{ ...btn, background: "#1a5c43", color: "#fff", border: 0, padding: "10px 18px" }}>
          {busy ? "Sending…" : "Send"}
        </button>
        <button onClick={onClose} style={btn}>Close</button>
      </div>
    </Modal>
  );
}

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(7,21,46,0.55)", zIndex: 100, display: "grid", placeItems: "center", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, padding: 24, width: "100%", maxWidth: 520, maxHeight: "90vh", overflow: "auto" }}>
        <h3 style={{ margin: "0 0 16px", fontSize: 16, color: "#17213a" }}>{title}</h3>
        {children}
      </div>
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18 }}>
      <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: accent || "#17213a", marginTop: 4 }}>{value}</div>
    </div>
  );
}

const chip = (bg: string, fg: string): React.CSSProperties => ({ display: "inline-block", padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: bg, color: fg, marginRight: 4 });
const th: React.CSSProperties = { textAlign: "left", padding: "12px 16px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5" };
const td: React.CSSProperties = { padding: "13px 16px", color: "#4b5563", verticalAlign: "top" };
const btn: React.CSSProperties = { background: "#fff", border: "1px solid #d7dce5", color: "#17213a", padding: "6px 12px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer", marginRight: 6 };
const lbl: React.CSSProperties = { display: "block", marginTop: 10, fontSize: 12, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600 };
const inp: React.CSSProperties = { display: "block", width: "100%", marginTop: 6, padding: "10px 12px", border: "1px solid #d7dce5", borderRadius: 8, fontSize: 13, boxSizing: "border-box", outline: "none" };