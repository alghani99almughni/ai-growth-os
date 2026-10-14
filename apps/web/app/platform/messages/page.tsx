"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function MessagesPage() {
  const [activeTab, setActiveTab] = useState<"whatsapp" | "whatsapp-promotional" | "email" | "messages">("whatsapp");
  const [items, setItems] = useState<any[]>([]);
  const [tenants, setTenants] = useState<any[]>([]);
  const [selectedInboxTenant, setSelectedInboxTenant] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [showCompose, setShowCompose] = useState(false);
  const [form, setForm] = useState({ tenant_id: "", subject: "", body: "", send_email: true });
  const [sending, setSending] = useState(false);
  const [campaignTenants, setCampaignTenants] = useState<string[]>([]);
  const [prospectLines, setProspectLines] = useState("");
  const [campaignChannels, setCampaignChannels] = useState<string[]>(["whatsapp"]);
  const [campaignSubject, setCampaignSubject] = useState("AI Growth OS update");
  const [campaignBody, setCampaignBody] = useState("");
  const [consentConfirmed, setConsentConfirmed] = useState(false);
  const [campaignBusy, setCampaignBusy] = useState(false);
  const [mediaUrl, setMediaUrl] = useState("");
  const [mediaType, setMediaType] = useState<"image" | "video" | "">("");
  const [mediaUploading, setMediaUploading] = useState(false);
  const [campaignResult, setCampaignResult] = useState<any>(null);
  const [emailInbox, setEmailInbox] = useState<any>({ items: [], configured: false });
  const [emailInboxLoading, setEmailInboxLoading] = useState(false);
  const [replyDrafts, setReplyDrafts] = useState<Record<string, string>>({});
  const [replySending, setReplySending] = useState<string>("");
  const [whatsappInbox, setWhatsappInbox] = useState<any>({ items: [], configured: false });
  const [whatsappInboxLoading, setWhatsappInboxLoading] = useState(false);
  const [whatsappReplyDrafts, setWhatsappReplyDrafts] = useState<Record<string, string>>({});
  const [whatsappReplySending, setWhatsappReplySending] = useState<string>("");
  const [replyTemplateItems, setReplyTemplateItems] = useState<any[]>([]);

  async function loadReplyTemplates() {
    try {
      const r = await fetch(api() + "/api/v1/platform/communications/templates", { headers: headers(), cache: "no-store" });
      const x = await r.json();
      if (r.ok) setReplyTemplateItems(x.items || []);
    } catch { /* templates remain optional; manual replies still work */ }
  }

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

  async function loadWhatsAppInbox() {
    setWhatsappInboxLoading(true);
    try {
      const r = await fetch(api() + "/api/v1/platform/tenant-comms/whatsapp/inbox?limit=200" + (selectedInboxTenant ? "&tenant_id=" + encodeURIComponent(selectedInboxTenant) : ""), { headers: headers(), cache: "no-store" });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Unable to load tenant WhatsApp inbox");
      setWhatsappInbox(x);
      await loadReplyTemplates();
      
    } catch (e: any) { setStatus(e.message || "Unable to load platform WhatsApp inbox"); }
    setWhatsappInboxLoading(false);
  }

  async function replyToWhatsApp(id: string) {
    const body = (whatsappReplyDrafts[id] || "").trim();
    if (!body) { setStatus("Enter a WhatsApp reply first."); return; }
    setWhatsappReplySending(id); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/tenant-comms/whatsapp/inbox/" + encodeURIComponent(id) + "/reply", {
        method: "POST", headers: headers(), body: JSON.stringify({ body }),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "WhatsApp reply failed");
      setWhatsappReplyDrafts(prev => ({ ...prev, [id]: "" }));
      setStatus("WhatsApp reply sent to " + x.phone);
      await loadWhatsAppInbox();
    } catch (e: any) { setStatus(e.message || "WhatsApp reply failed"); }
    setWhatsappReplySending("");
  }

  async function loadEmailInbox() {
    setEmailInboxLoading(true);
    try {
      const r = await fetch(api() + "/api/v1/platform/tenant-comms/email/inbox?limit=200" + (selectedInboxTenant ? "&tenant_id=" + encodeURIComponent(selectedInboxTenant) : ""), { headers: headers(), cache: "no-store" });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Unable to load tenant email inbox");
      setEmailInbox(x);
      await loadReplyTemplates();
      
    } catch (e: any) { setStatus(e.message || "Unable to load platform inbox"); }
    setEmailInboxLoading(false);
  }

  async function replyToEmail(id: string) {
    const body = (replyDrafts[id] || "").trim();
    if (!body) { setStatus("Enter a reply first."); return; }
    setReplySending(id); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/tenant-comms/email/inbox/" + encodeURIComponent(id) + "/reply", {
        method: "POST", headers: headers(), body: JSON.stringify({ body }),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Email reply failed");
      setReplyDrafts(prev => ({ ...prev, [id]: "" }));
      setStatus("Email reply sent to " + x.to + " through the tenant mailbox.");
      await loadEmailInbox();
    } catch (e: any) { setStatus(e.message || "Email reply failed"); }
    setReplySending("");
  }

  function importProspectCsv(file?: File) {
    if (!file) return;
    void file.text().then(text => {
      setProspectLines(text.split(/\\r?\\n/).filter(Boolean).map(line => line.split(/[;,]/).map(v => v.trim()).join(",")).join("\\n"));
      setStatus("Contact CSV loaded. Review the rows and confirm opt-in before sending.");
    }).catch(() => setStatus("Could not read that CSV file."));
  }

  const whatsappTemplates: Record<string, string> = {
    announcement: "Hello {{name}}, we have an update from AI Growth OS. Reply to this message if you would like more details.",
    onboarding: "Hello {{name}}, your AI Growth OS workspace is ready. Reply if you need help getting started.",
    support: "Hello {{name}}, our support team has an update on your request. Reply here if you still need assistance.",
  };

  async function uploadCampaignMedia(file?: File) {
    if (!file) return;
    if (!file.type.startsWith("image/") && !file.type.startsWith("video/")) { setStatus("Choose an image or video file."); return; }
    if (file.size > 16 * 1024 * 1024) { setStatus("Media upload limit is 16 MB."); return; }
    const data = new FormData(); data.append("file", file);
    setMediaUploading(true); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/communications/media", {
        method: "POST",
        headers: { Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || "") },
        body: data,
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Media upload failed");
      setMediaUrl(x.media_url);
      setMediaType(file.type.startsWith("video/") ? "video" : "image");
      setStatus("Media uploaded to durable storage. It will be sent with the WhatsApp campaign.");
    } catch (e: any) { setStatus(e.message || "Media upload failed"); }
    setMediaUploading(false);
  }

  async function sendCampaign() {
    if (!campaignTenants.length && !prospectLines.trim()) { setStatus("Select tenants or paste prospect contacts."); return; }
    if (!campaignChannels.length) { setStatus("Choose WhatsApp and/or email."); return; }
    if (!campaignBody.trim()) { setStatus("Enter a campaign message."); return; }
    if (!consentConfirmed) { setStatus("Confirm opt-in/consent for every selected recipient."); return; }
    const recipients = prospectLines.split(/\r?\n/).map(line => line.trim()).filter(Boolean).map(line => {
      const parts = line.split(",").map(x => x.trim());
      return { name: parts[0] || "", phone: parts[1] || null, email: parts[2] || null };
    });
    if (!campaignTenants.length && !recipients.length) { setStatus("Select tenants or paste prospect contacts."); return; }
    if (recipients.some(r => !r.phone && !r.email)) { setStatus("Each prospect line needs a phone and/or email: name,phone,email"); return; }
    setCampaignBusy(true); setStatus(""); setCampaignResult(null);
    try {
      const r = await fetch(api() + "/api/v1/platform/communications/campaign", {
        method: "POST", headers: headers(),
        body: JSON.stringify({ tenant_ids: campaignTenants, recipients, channels: campaignChannels, subject: campaignSubject, body: campaignBody, consent_confirmed: consentConfirmed, media_url: mediaUrl || null, media_type: mediaType || null }),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Campaign failed");
      setCampaignResult(x);
      setStatus("Campaign processed: " + x.sent + " successful channel deliveries across " + x.selected + " selected tenants.");
    } catch (e: any) { setStatus(e.message || "Campaign failed"); }
    setCampaignBusy(false);
  }

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
      <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18, marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, color: "#17213a" }}>AI Growth OS Marketing Hub</h1>
        <p style={{ margin: "6px 0 14px", color: "#75839a", fontSize: 13 }}>Campaigns, WhatsApp and email in one dashboard workspace.</p>
        <div role="tablist" style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {([{id:"whatsapp",label:"WhatsApp Inbox"},{id:"whatsapp-promotional",label:"WhatsApp Promotional"},{id:"email",label:"Email Inbox"},{id:"messages",label:"Tenant Messages"}] as const).map(tab => <button key={tab.id} role="tab" aria-selected={activeTab===tab.id} onClick={() => setActiveTab(tab.id)} style={{ padding:"9px 15px", borderRadius:9, border:"1px solid "+(activeTab===tab.id?"#5b5cf0":"#d7dce5"), background:activeTab===tab.id?"#5b5cf0":"#fff", color:activeTab===tab.id?"#fff":"#344054", fontWeight:650, cursor:"pointer" }}>{tab.label}</button>)}
        </div>
      </section>
      <>
      {activeTab === "whatsapp-promotional" && (
      <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>AI Growth OS Marketing Hub</h1>
        <p style={{ margin: "6px 0 16px", color: "#75839a", fontSize: 13 }}>One workspace for WhatsApp and email campaigns, prospect contacts, platform inboxes, replies, and delivery results. Campaigns use AI Growth OS platform-owned channels, not tenant credentials.</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 14 }}>
          <label style={{ fontSize: 12, color: "#17213a", fontWeight: 600 }}>Select tenant recipients
            <select multiple value={campaignTenants} onChange={e => setCampaignTenants(Array.from(e.target.selectedOptions, o => o.value))} style={{ ...inputStyle, minHeight: 130 }}>
              {tenants.map((t: any) => <option key={t.id} value={t.id}>{t.name}{t.email ? " · " + t.email : ""}</option>)}
            </select>
            <span style={{ display: "block", marginTop: 5, color: "#75839a", fontWeight: 400 }}>Use Ctrl-click to select multiple tenants.</span>
          </label>
          <div style={{ display: "grid", gap: 12, alignContent: "start" }}>
            <div style={{ fontSize: 12, color: "#17213a", fontWeight: 600 }}>Delivery channels</div>
            {["whatsapp"].map(channel => <label key={channel} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#4b5563" }}>
              <input type="checkbox" checked={campaignChannels.includes(channel)} onChange={e => setCampaignChannels(prev => e.target.checked ? [...prev, channel] : prev.filter(x => x !== channel))} />
              Platform WhatsApp
            </label>)}
            <label style={{ fontSize: 12, color: "#17213a", fontWeight: 600 }}>Email subject
              <input value={campaignSubject} onChange={e => setCampaignSubject(e.target.value)} style={inputStyle} />
            </label>
          </div>
        </div>
        <label style={{ display: "block", marginTop: 14, fontSize: 12, color: "#17213a", fontWeight: 600 }}>Prospect contact list (optional)
          <textarea value={prospectLines} onChange={e => setProspectLines(e.target.value)} rows={4} placeholder={"One contact per line: name,phone,email\nExample: Ayesha,+919876543210,ayesha@example.com"} style={{ ...inputStyle, fontFamily: "monospace", resize: "vertical" }} />
          <span style={{ display: "block", marginTop: 5, color: "#75839a", fontWeight: 400 }}>Paste only contacts who have opted in. You can send to selected tenants, prospects, or both.</span>
        </label>
        <label style={{ display: "block", marginTop: 10, fontSize: 12, color: "#17213a", fontWeight: 600 }}>Import contacts from CSV
          <input type="file" accept=".csv,text/csv" onChange={e => importProspectCsv(e.target.files?.[0])} style={{ ...inputStyle, padding: 8 }} />
          <span style={{ display: "block", marginTop: 4, color: "#75839a", fontWeight: 400 }}>Columns: name,phone,email. Imported rows remain editable above.</span>
        </label>
        <label style={{ display: "block", marginTop: 14, fontSize: 12, color: "#17213a", fontWeight: 600 }}>Optional WhatsApp image/video (max 16 MB)
          <input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,video/3gpp" onChange={e => uploadCampaignMedia(e.target.files?.[0])} disabled={mediaUploading} style={{ ...inputStyle, padding: 8 }} />
          <span style={{ display: "block", marginTop: 4, color: "#75839a", fontWeight: 400 }}>{mediaUploading ? "Uploading…" : mediaUrl ? "Uploaded: " + mediaType + " · ready for WhatsApp campaign" : "Requires S3-compatible durable storage and Meta WhatsApp Cloud API credentials."}</span>
          {mediaUrl && <button type="button" onClick={() => { setMediaUrl(""); setMediaType(""); }} style={{ marginTop: 6, border: "1px solid #d7dce5", borderRadius: 7, padding: "5px 9px", background: "#fff" }}>Remove media</button>}
        </label>
        <label style={{ display: "block", marginTop: 14, fontSize: 12, color: "#17213a", fontWeight: 600 }}>Message template
          <select defaultValue="" onChange={e => { if (e.target.value) setCampaignBody(whatsappTemplates[e.target.value] || ""); }} style={inputStyle}>
            <option value="">Choose a starter template…</option>
            <option value="announcement">Announcement</option>
            <option value="onboarding">Tenant onboarding</option>
            <option value="support">Support update</option>
          </select>
          <span style={{ display: "block", marginTop: 4, color: "#75839a", fontWeight: 400 }}>These are editable text starters, not Meta-approved WhatsApp templates.</span>
        </label>
        <label style={{ display: "block", marginTop: 14, fontSize: 12, color: "#17213a", fontWeight: 600 }}>Message
          <textarea value={campaignBody} onChange={e => setCampaignBody(e.target.value)} rows={4} maxLength={4000} placeholder="Write the message…" style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }} />
        </label>
        <label style={{ display: "flex", gap: 9, alignItems: "flex-start", marginTop: 14, fontSize: 12, lineHeight: 1.5, color: "#4b5563" }}>
          <input type="checkbox" checked={consentConfirmed} onChange={e => setConsentConfirmed(e.target.checked)} style={{ marginTop: 2 }} />
          I confirm every selected recipient opted in and required opt-out rules are respected.
        </label>
        <button onClick={sendCampaign} disabled={campaignBusy} style={{ marginTop: 14, background: "#4f46e5", color: "#fff", border: 0, padding: "11px 18px", borderRadius: 9, fontWeight: 700, cursor: campaignBusy ? "wait" : "pointer" }}>
          {campaignBusy ? "Sending…" : "Send campaign"}
        </button>
        {campaignResult && <div style={{ marginTop: 14, borderTop: "1px solid #edf0f5", paddingTop: 12, fontSize: 12, color: "#4b5563" }}>
          <strong>Delivery results</strong>
          {campaignResult.results?.map((r: any) => <div key={r.tenant_id} style={{ padding: "8px 0", borderBottom: "1px solid #f1f4f8" }}>
            <strong>{r.tenant_name}</strong> — {Object.entries(r.channels || {}).map(([c, v]: any) => c + ": " + (v.status || (v.sent ? "sent" : "failed"))).join(" · ")}
          </div>)}
        </div>}
      </section>
      )}
      {activeTab === "whatsapp" && (
      <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, color: "#17213a" }}>Tenant WhatsApp Inbox</h2>
            <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>View and reply using each tenant’s already-connected WhatsApp channel.</p>
          </div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            <a href="/platform/templates" style={{background:"#f0efff",border:"1px solid #d9d5ff",borderRadius:9,padding:"9px 14px",color:"#4f46e5",fontSize:12,fontWeight:700,textDecoration:"none"}}>Reply templates & auto-reply</a>
            <button onClick={loadWhatsAppInbox} disabled={whatsappInboxLoading} style={{ background: "#fff", border: "1px solid #d7dce5", borderRadius: 9, padding: "9px 14px", cursor: whatsappInboxLoading ? "wait" : "pointer", fontWeight: 600 }}>
              {whatsappInboxLoading ? "Loading…" : "Refresh WhatsApp inbox"}
            </button>
          </div>
        </div>
        <label style={{display:"block",marginTop:14,fontSize:12,color:"#344054"}}>Tenant filter (all tenants by default)<select value={selectedInboxTenant} onChange={e=>setSelectedInboxTenant(e.target.value)} style={inputStyle}><option value="">All tenants</option>{tenants.map((t:any)=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
        {!whatsappInbox.configured || !whatsappInbox.webhook_secret_configured ? <p style={{ color: "#8a5a00", background: "#fff8e6", padding: 10, borderRadius: 8, fontSize: 12 }}>The inbox uses existing tenant webhook connections; no separate platform WhatsApp credentials are required.</p> : null}
        {(whatsappInbox.items || []).length === 0 ? <p style={{ color: "#75839a", fontSize: 13, marginTop: 18 }}>No tenant WhatsApp messages stored yet. New inbound messages appear after the tenant webhook receives them.</p> :
          whatsappInbox.items.map((m: any) => <div key={m.id} style={{ borderTop: "1px solid #edf0f5", marginTop: 14, paddingTop: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <strong style={{ color: "#17213a" }}>{m.contact_name || m.phone} · {m.tenant_name}</strong>
              <span style={{ color: "#75839a", fontSize: 11 }}>{m.created_at ? new Date(m.created_at).toLocaleString() : ""} · {m.direction} · {m.status}</span>
            </div>
            <div style={{ color: "#4b5563", fontSize: 12, margin: "5px 0" }}>{m.phone}</div>
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 13, color: "#4b5563", background: "#fafbfd", borderRadius: 8, padding: 12 }}>{m.body}</pre>
            {m.direction === "inbound" && m.status !== "replied" && <div style={{ display: "grid", gap: 8 }}>
              <select defaultValue="" aria-label="Insert WhatsApp reply template" onChange={e => { const t = replyTemplateItems.find((item: any) => item.id === e.target.value); if (t) setWhatsappReplyDrafts(prev => ({ ...prev, [m.id]: t.body })); }} style={inputStyle}><option value="">Insert a saved WhatsApp template…</option>{replyTemplateItems.filter((t: any) => t.channel === "whatsapp" && t.is_active).map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
              <textarea value={whatsappReplyDrafts[m.id] || ""} onChange={e => setWhatsappReplyDrafts(prev => ({ ...prev, [m.id]: e.target.value }))} rows={2} placeholder={"Reply to " + m.phone} style={{ ...inputStyle, fontFamily: "inherit" }} />
              <button onClick={() => replyToWhatsApp(m.id)} disabled={whatsappReplySending === m.id} style={{ justifySelf: "start", background: "#12805c", color: "#fff", border: 0, padding: "9px 14px", borderRadius: 8, fontWeight: 700, cursor: "pointer" }}>{whatsappReplySending === m.id ? "Sending…" : "Reply on WhatsApp"}</button>
            </div>}
          </div>)}
      </section>
      )}

      {activeTab === "email" && (
      <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, color: "#17213a" }}>Tenant Email Inbox</h2>
            <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>View and reply using each tenant’s connected mailbox.</p>
          </div>
          <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
            <a href="/platform/templates" style={{background:"#f0efff",border:"1px solid #d9d5ff",borderRadius:9,padding:"9px 14px",color:"#4f46e5",fontSize:12,fontWeight:700,textDecoration:"none"}}>Reply templates & auto-reply</a>
            <button onClick={loadEmailInbox} disabled={emailInboxLoading} style={{ background: "#fff", border: "1px solid #d7dce5", borderRadius: 9, padding: "9px 14px", cursor: emailInboxLoading ? "wait" : "pointer", fontWeight: 600 }}>
              {emailInboxLoading ? "Checking inbox…" : "Refresh inbox"}
            </button>
          </div>
        </div>
        {emailInbox.from_address && <p style={{ fontSize: 12, color: "#4b5563" }}>Mailbox: {emailInbox.from_address}</p>}
        {emailInbox.poll_error && <p style={{ color: "#b6341f", fontSize: 12 }}>{emailInbox.poll_error}</p>}
        {!emailInbox.configured && <p style={{ color: "#8a5a00", background: "#fff8e6", padding: 10, borderRadius: 8, fontSize: 12 }}>This inbox reads existing tenant mailbox logs and replies through the selected tenant’s encrypted SMTP configuration.</p>}
        <label style={{display:"block",marginTop:14,fontSize:12,color:"#344054"}}>Tenant filter (all tenants by default)<select value={selectedInboxTenant} onChange={e=>setSelectedInboxTenant(e.target.value)} style={inputStyle}><option value="">All tenants</option>{tenants.map((t:any)=><option key={t.id} value={t.id}>{t.name}</option>)}</select></label>
        {(emailInbox.items || []).length === 0 ? <p style={{ color: "#75839a", fontSize: 13, marginTop: 18 }}>No tenant email log entries yet. New messages appear after tenant mailbox polling processes them.</p> :
          emailInbox.items.map((m: any) => <div key={m.id} style={{ borderTop: "1px solid #edf0f5", marginTop: 14, paddingTop: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <strong style={{ color: "#17213a" }}>{m.subject || "(no subject)"} · {m.tenant_name}</strong>
              <span style={{ color: "#75839a", fontSize: 11 }}>{m.created_at ? new Date(m.created_at).toLocaleString() : ""} · {m.outcome}</span>
            </div>
            <div style={{ color: "#4b5563", fontSize: 12, margin: "5px 0" }}>From: {m.from_address}</div>
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 13, color: "#4b5563", background: "#fafbfd", borderRadius: 8, padding: 12, maxHeight: 180, overflow: "auto" }}>{m.body || "(No stored body for older email log)"}</pre>
            {m.outcome === "admin_replied" ? <p style={{ color: "#1d9c68", fontSize: 12 }}>Admin reply: {m.reply_text}</p> :
              <div style={{ display: "grid", gap: 8 }}>
                <select defaultValue="" aria-label="Insert email reply template" onChange={e => { const t = replyTemplateItems.find((item: any) => item.id === e.target.value); if (t) setReplyDrafts(prev => ({ ...prev, [m.id]: t.body })); }} style={inputStyle}><option value="">Insert a saved email template…</option>{replyTemplateItems.filter((t: any) => t.channel === "email" && t.is_active).map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
                <textarea value={replyDrafts[m.id] || ""} onChange={e => setReplyDrafts(prev => ({ ...prev, [m.id]: e.target.value }))} rows={3} placeholder={"Reply to " + m.from_address} style={{ ...inputStyle, fontFamily: "inherit" }} />
                <button onClick={() => replyToEmail(m.id)} disabled={replySending === m.id} style={{ justifySelf: "start", background: "#4f46e5", color: "#fff", border: 0, padding: "9px 14px", borderRadius: 8, fontWeight: 700, cursor: "pointer" }}>{replySending === m.id ? "Sending…" : "Reply by email"}</button>
              </div>}
          </div>)}
      </section>
      )}

      {activeTab === "messages" && (
      <>
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

      </>
      )}
      </>
    </div>
  );
}

const inputStyle: React.CSSProperties = { display: "block", width: "100%", marginTop: 6, padding: 10, borderRadius: 8, border: "1px solid #d7dce5", fontSize: 13, outline: "none" };
const thStyle: React.CSSProperties = { textAlign: "left", padding: "12px 16px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5" };
const tdStyle: React.CSSProperties = { padding: "13px 16px", color: "#4b5563", verticalAlign: "top" };
