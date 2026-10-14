"use client";

import { useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Recipient = { name: string; phone: string; email: string };

export default function PlatformCustomerMarketingPage() {
  const [contactsCsv, setContactsCsv] = useState("");
  const [channels, setChannels] = useState<string[]>(["whatsapp"]);
  const [subject, setSubject] = useState("AI Growth OS update");
  const [body, setBody] = useState("");
  const [consentConfirmed, setConsentConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [result, setResult] = useState<any>(null);

  function headers() {
    return {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || ""),
    };
  }

  function parseContacts(text: string): Recipient[] {
    return text.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
      const parts = line.split(",").map(value => value.trim());
      return { name: parts[0] || "", phone: parts[1] || "", email: parts[2] || "" };
    });
  }

  function importCsv(file?: File) {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result || "");
      const rows = text.split(/\r?\n/).filter(Boolean);
      const header = (rows[0] || "").toLowerCase();
      const hasHeader = header.includes("phone") || header.includes("email") || header.includes("name");
      const data = rows.slice(hasHeader ? 1 : 0);
      setContactsCsv(data.map(row => row.split(",").map(v => v.trim()).join(",")).join("\n"));
      setStatus("Imported " + data.length + " contact rows. Review the list before sending.");
    };
    reader.readAsText(file);
  }

  async function sendCampaign() {
    const recipients = parseContacts(contactsCsv);
    if (!recipients.length) { setStatus("Import or paste your own customer contacts first."); return; }
    if (recipients.some(r => !r.phone && !r.email)) { setStatus("Every row needs a phone number and/or email: name,phone,email."); return; }
    if (!channels.length) { setStatus("Select WhatsApp and/or email."); return; }
    if (!body.trim()) { setStatus("Enter your campaign message."); return; }
    if (!consentConfirmed) { setStatus("Confirm that these are your own opted-in contacts."); return; }

    setBusy(true); setStatus(""); setResult(null);
    try {
      const response = await fetch(api() + "/api/v1/platform/communications/campaign", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify({
          recipients: recipients.map(r => ({ name: r.name, phone: r.phone || null, email: r.email || null })),
          channels, subject, body, consent_confirmed: consentConfirmed,
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail || "Campaign failed");
      setResult(data);
      setStatus("Processed " + data.selected + " of your contacts; " + data.sent + " channel deliveries reported successful.");
    } catch (error: any) {
      setStatus(error?.message || "Campaign failed");
    } finally {
      setBusy(false);
    }
  }

  const inputStyle: React.CSSProperties = { display: "block", width: "100%", marginTop: 6, padding: 11, borderRadius: 8, border: "1px solid #d7dce5", fontSize: 13, boxSizing: "border-box" };

  return <main style={{ maxWidth: 1080, margin: "0 auto", padding: 28, color: "#17213a" }}>
    <header style={{ marginBottom: 24 }}>
      <p style={{ margin: "0 0 8px", color: "#5b5cf0", fontWeight: 800, fontSize: 11, letterSpacing: ".12em" }}>AI GROWTH OS · PLATFORM MARKETING</p>
      <h1 style={{ margin: 0, fontSize: 28, letterSpacing: "-.03em" }}>Your Customer Campaigns</h1>
      <p style={{ color: "#667085", fontSize: 14, lineHeight: 1.6, maxWidth: 760 }}>Send campaigns to your own customers and prospects outside AI Growth OS. Uses your platform-connected WhatsApp and email senders only. No tenant accounts, tenant inboxes, or tenant customer lists are involved.</p>
    </header>

    <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(240px,1fr))", gap: 14, marginBottom: 18 }}>
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 12, padding: 18 }}>
        <h2 style={{ margin: "0 0 8px", fontSize: 14 }}>Your WhatsApp sender</h2>
        <p style={{ margin: 0, color: "#667085", fontSize: 12, lineHeight: 1.6 }}>Uses the platform WhatsApp provider configured by the Super Admin. Configure credentials in Render environment settings.</p>
      </div>
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 12, padding: 18 }}>
        <h2 style={{ margin: "0 0 8px", fontSize: 14 }}>Your email sender</h2>
        <p style={{ margin: 0, color: "#667085", fontSize: 12, lineHeight: 1.6 }}>Uses the platform Resend or SMTP sender. Tenant mailbox settings are not used.</p>
      </div>
    </section>

    <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginBottom: 18 }}>
      <h2 style={{ margin: "0 0 14px", fontSize: 17 }}>1. Your external customer list</h2>
      <label style={{ display: "block", fontSize: 12, fontWeight: 700 }}>Import CSV
        <input type="file" accept=".csv,text/csv" onChange={e => importCsv(e.target.files?.[0])} style={inputStyle} />
      </label>
      <p style={{ color: "#667085", fontSize: 12 }}>CSV columns: name,phone,email. Or paste one contact per line below. Use international phone numbers. Contacts are not read from tenant records.</p>
      <label style={{ display: "block", fontSize: 12, fontWeight: 700 }}>Contact rows
        <textarea value={contactsCsv} onChange={e => setContactsCsv(e.target.value)} rows={7} placeholder={"name,phone,email\nAyesha,+919876543210,ayesha@example.com"} style={{ ...inputStyle, fontFamily: "monospace", resize: "vertical" }} />
      </label>
      <p style={{ margin: "8px 0 0", color: "#8a5a00", fontSize: 12 }}>Current version: imported contacts are submitted with this campaign; a persistent contact CRM/list manager is the next integration step.</p>
    </section>

    <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginBottom: 18 }}>
      <h2 style={{ margin: "0 0 14px", fontSize: 17 }}>2. Campaign setup</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 14 }}>
        <div>
          <p style={{ margin: "0 0 8px", fontSize: 12, fontWeight: 700 }}>Send using</p>
          {["whatsapp", "email"].map(channel => <label key={channel} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 10, fontSize: 13 }}>
            <input type="checkbox" checked={channels.includes(channel)} onChange={e => setChannels(old => e.target.checked ? [...old, channel] : old.filter(value => value !== channel))} />
            {channel === "whatsapp" ? "My platform WhatsApp" : "My platform email"}
          </label>)}
        </div>
        <label style={{ fontSize: 12, fontWeight: 700 }}>Email subject
          <input value={subject} onChange={e => setSubject(e.target.value)} style={inputStyle} />
        </label>
      </div>
      <label style={{ display: "block", marginTop: 14, fontSize: 12, fontWeight: 700 }}>Message
        <textarea value={body} onChange={e => setBody(e.target.value)} rows={6} placeholder={"Hi {{name}}, ..."} style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }} />
      </label>
      <p style={{ color: "#667085", fontSize: 12 }}>Personalization token supported: {{name}}. WhatsApp Business template rules may apply to business-initiated messages.</p>
      <label style={{ display: "flex", gap: 9, alignItems: "flex-start", marginTop: 14, fontSize: 12, lineHeight: 1.5 }}>
        <input type="checkbox" checked={consentConfirmed} onChange={e => setConsentConfirmed(e.target.checked)} style={{ marginTop: 2 }} />
        I confirm these are my own contacts and the selected recipients have consented to receive the selected channel's messages.
      </label>
      <button onClick={sendCampaign} disabled={busy} style={{ marginTop: 18, background: "#4f46e5", color: "#fff", border: 0, padding: "12px 20px", borderRadius: 9, fontWeight: 800, cursor: busy ? "wait" : "pointer" }}>{busy ? "Sending campaign…" : "Send campaign to my customers"}</button>
      {status && <p role="status" style={{ marginTop: 14, fontSize: 13, color: status.includes("failed") ? "#b42318" : "#344054" }}>{status}</p>}
    </section>

    {result && <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22 }}>
      <h2 style={{ margin: "0 0 12px", fontSize: 17 }}>3. Delivery results</h2>
      {(result.results || []).map((row: any, index: number) => <div key={row.name + "-" + index} style={{ borderTop: "1px solid #edf0f5", padding: "12px 0", fontSize: 13 }}>
        <strong>{row.name || "Customer"}</strong>
        <div style={{ color: "#667085", marginTop: 5 }}>{Object.entries(row.channels || {}).map(([channel, value]: any) => channel + ": " + (value.status || (value.sent ? "sent" : "failed"))).join(" · ")}</div>
      </div>)}
    </section>}
  </main>;
}
