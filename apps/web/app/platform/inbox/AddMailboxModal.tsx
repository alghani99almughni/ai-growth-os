"use client";
import { useState } from "react";

const api = () =>
  String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export default function AddMailboxModal({
  tenantId,
  token,
  onClose,
  onDone,
}: {
  tenantId: string;
  token: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form, setForm] = useState({
    provider: "gmail",
    email_address: "",
    label: "Platform mailbox",
    role: "support",
    imap_host: "",
    imap_port: 993,
    imap_user: "",
    imap_password: "",
    smtp_host: "",
    smtp_port: 465,
    smtp_user: "",
    smtp_password: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function upd(k: string, v: any) {
    setForm((p) => ({ ...p, [k]: v }));
  }

  async function submit() {
    setBusy(true); setErr("");
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
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify(payload),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Could not connect mailbox");
      onDone();
    } catch (e: any) {
      setErr(e.message || "Could not connect mailbox");
    }
    setBusy(false);
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(15,23,42,0.5)",
        display: "grid", placeItems: "center", zIndex: 100, padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff", borderRadius: 16, padding: 24, width: "100%",
          maxWidth: 560, maxHeight: "92vh", overflowY: "auto",
          boxShadow: "0 24px 60px rgba(0,0,0,0.25)",
        }}
      >
        <h2 style={{ margin: 0, fontSize: 20, color: "#17213a" }}>Connect platform mailbox</h2>
        <p style={{ margin: "6px 0 18px", color: "#75839a", fontSize: 13 }}>
          This mailbox belongs to the platform, not any tenant.
        </p>

        {err && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{err}</p>}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <label style={lbl}>
            Provider
            <select value={form.provider} onChange={(e) => upd("provider", e.target.value)} style={inp}>
              <option value="gmail">Gmail (App Password)</option>
              <option value="outlook">Outlook / Microsoft 365</option>
              <option value="custom">Custom SMTP / IMAP</option>
            </select>
          </label>

          <label style={lbl}>
            Role
            <select value={form.role} onChange={(e) => upd("role", e.target.value)} style={inp}>
              <option value="support">support@</option>
              <option value="contact">contact@</option>
              <option value="billing">billing@</option>
              <option value="general">general</option>
            </select>
          </label>

          <label style={{ ...lbl, gridColumn: "1 / -1" }}>
            Label
            <input value={form.label} onChange={(e) => upd("label", e.target.value)} style={inp} />
          </label>

          <label style={{ ...lbl, gridColumn: "1 / -1" }}>
            Email address
            <input
              value={form.email_address}
              onChange={(e) => upd("email_address", e.target.value)}
              placeholder="admin@yourdomain.com"
              style={inp}
            />
          </label>

          {form.provider === "custom" && (
            <>
              <label style={lbl}>IMAP host<input value={form.imap_host} onChange={(e) => upd("imap_host", e.target.value)} style={inp} /></label>
              <label style={lbl}>IMAP port<input type="number" value={form.imap_port} onChange={(e) => upd("imap_port", Number(e.target.value))} style={inp} /></label>
              <label style={lbl}>SMTP host<input value={form.smtp_host} onChange={(e) => upd("smtp_host", e.target.value)} style={inp} /></label>
              <label style={lbl}>SMTP port<input type="number" value={form.smtp_port} onChange={(e) => upd("smtp_port", Number(e.target.value))} style={inp} /></label>
            </>
          )}

          <label style={lbl}>
            IMAP/SMTP user
            <input value={form.imap_user} onChange={(e) => upd("imap_user", e.target.value)} placeholder="usually the email address" style={inp} />
          </label>
          <label style={lbl}>
            Password / App password
            <input type="password" value={form.imap_password} onChange={(e) => upd("imap_password", e.target.value)} style={inp} />
          </label>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 20 }}>
          <button onClick={onClose} disabled={busy} style={btnGhost}>Cancel</button>
          <button
            onClick={submit}
            disabled={busy || !form.email_address || !form.imap_password}
            style={{ ...btnPrimary, opacity: busy || !form.email_address || !form.imap_password ? 0.6 : 1 }}
          >
            {busy ? "Connecting…" : "Connect mailbox"}
          </button>
        </div>
      </div>
    </div>
  );
}

const lbl: React.CSSProperties = { display: "block", fontSize: 12, color: "#4b5563", fontWeight: 600 };
const inp: React.CSSProperties = {
  display: "block", width: "100%", marginTop: 6, padding: 10, borderRadius: 8,
  border: "1px solid #d7dce5", fontSize: 13, outline: "none", boxSizing: "border-box",
};
const btnGhost: React.CSSProperties = {
  padding: "10px 18px", border: "1px solid #d7dce5", background: "#fff",
  borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: "pointer", color: "#17213a",
};
const btnPrimary: React.CSSProperties = {
  padding: "10px 18px", border: 0, background: "linear-gradient(135deg,#5b5cf0,#7159f7)",
  color: "#fff", borderRadius: 10, fontSize: 13, fontWeight: 700, cursor: "pointer",
};