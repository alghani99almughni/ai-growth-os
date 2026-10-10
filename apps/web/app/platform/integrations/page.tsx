"use client";
import { useEffect, useState } from "react";
const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
type Channel = "email" | "whatsapp";
type Tab = "inbox" | "campaigns" | "settings";
type PlatformStatus = { company_name: string; support_email: string; email_configured: boolean; email_from: string; whatsapp_configured: boolean; whatsapp_provider: string; campaign_contact_limit: number };
const sampleContacts = [
  { name: "Ayesha", email: "ayesha@example.com", phone: "+919876543210", email_opt_in: true, whatsapp_opt_in: false },
  { name: "Rahul", email: "rahul@example.com", phone: "+919876543211", email_opt_in: false, whatsapp_opt_in: true }
];
export default function PlatformCommunicationsPage() {
  const [tab, setTab] = useState<Tab>("inbox");
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<PlatformStatus | null>(null);
  const [tickets, setTickets] = useState<any[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [channel, setChannel] = useState<Channel>("whatsapp");
  const [campaignName, setCampaignName] = useState("New tenant outreach");
  const [subject, setSubject] = useState("Grow your business with AI Growth OS");
  const [templateName, setTemplateName] = useState("re_engagement");
  const [body, setBody] = useState("Hi {{name}},\\n\\nDiscover how AI Growth OS can help {{company}} businesses capture leads, answer enquiries and manage bookings 24/7. Reply to learn more.");
  const [contactsJson, setContactsJson] = useState(JSON.stringify(sampleContacts, null, 2));
  const [sending, setSending] = useState(false);
  const [campaignResult, setCampaignResult] = useState<any>(null);
  async function request(path: string, init: RequestInit = {}) {
    const r = await fetch(API + path, { ...init, headers: { Authorization: "Bearer " + token, ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers || {}) }, cache: "no-store" });
    const raw = await r.text(); let data: any = {}; try { data = raw ? JSON.parse(raw) : {}; } catch {}
    if (!r.ok) throw new Error(data.detail || "Request failed (" + r.status + ")");
    return data;
  }
  async function refresh() {
    if (!token) return; setLoading(true); setError("");
    try {
      const [s,t,m] = await Promise.all([request("/api/v1/platform/communications/status"), request("/api/v1/platform/tickets?limit=100"), request("/api/v1/platform/messages?limit=100")]);
      setStatus(s); setTickets(safeItems(t)); setMessages(safeItems(m));
    } catch (e: any) { setError(e.message || "Could not load platform communications."); } finally { setLoading(false); }
  }
  useEffect(() => { setToken(localStorage.getItem("ago_access_token") || ""); }, []);
  useEffect(() => { if (token) void refresh(); }, [token]);
  async function sendCampaign() {
    setSending(true); setError(""); setCampaignResult(null);
    try {
      let contacts: any; try { contacts = JSON.parse(contactsJson); } catch { throw new Error("Contacts must be valid JSON. Use the sample format and add your opted-in contacts."); }
      if (!Array.isArray(contacts) || contacts.length === 0) throw new Error("Add at least one contact.");
      const result = await request("/api/v1/platform/communications/campaigns/send", { method: "POST", body: JSON.stringify({ name: campaignName, channel, subject, template_name: templateName, body, contacts }) });
      setCampaignResult(result);
    } catch (e: any) { setError(e.message || "Campaign send failed."); } finally { setSending(false); }
  }
  return <div>
    <header style={{ marginBottom: 22, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
      <div><p style={{ margin: "0 0 7px", color: "#14856b", fontSize: 11, fontWeight: 800, letterSpacing: ".12em" }}>PLATFORM OPERATIONS</p><h1 style={{ margin: 0, fontSize: 28, letterSpacing: "-.035em", color: "#17213a" }}>Communications centre</h1><p style={{ margin: "7px 0 0", color: "#75839a", fontSize: 13 }}>Your platform-owned inbox and outreach campaigns. No tenant login or tenant credentials required.</p></div>
      <button onClick={() => void refresh()} disabled={loading} style={secondaryButton}>{loading ? "Refreshing…" : "Refresh data"}</button>
    </header>
    {error && <div role="alert" style={{ padding: 13, marginBottom: 14, color: "#a12b2b", background: "#fff1f0", border: "1px solid #ffd8d4", borderRadius: 10 }}>{error}</div>}
    <ProviderSetup token={token} onError={setError} />
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 12, marginBottom: 20 }}>
      <Stat label="Tenant support tickets" value={tickets.length} detail="Across the platform" />
      <Stat label="Platform messages" value={messages.length} detail="Sent from Super Admin" />
      <Stat label="Email channel" value={status ? status.email_configured ? "Configured" : "Not configured" : "—"} detail={status?.email_from || "Requires platform email provider"} good={!!status?.email_configured} />
      <Stat label="WhatsApp channel" value={status ? status.whatsapp_configured ? "Configured" : "Not configured" : "—"} detail={status?.whatsapp_provider || "Requires platform WhatsApp provider"} good={!!status?.whatsapp_configured} />
    </div>
    <nav style={{ display: "flex", gap: 5, borderBottom: "1px solid #e1e7ef", marginBottom: 18, overflowX: "auto" }}>
      {([["inbox","Support inbox"],["campaigns","Marketing campaigns"],["settings","Channel status"]] as [Tab,string][]).map(([key,label]) => <button key={key} onClick={() => setTab(key)} style={tabStyle(tab === key)}>{label}</button>)}
    </nav>
    {loading && <p style={{ color: "#75839a" }}>Loading platform communication data…</p>}
    {!loading && tab === "inbox" && <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))", gap: 16 }}>
      <section style={panel}><SectionHeading title="Tenant support queue" subtitle="Review support issues from one place." />
        {tickets.length === 0 ? <Empty text="No support tickets found." /> : tickets.slice(0,30).map((t,i) => <div key={t.id || i} style={listRow}><div style={{ display:"flex", justifyContent:"space-between", gap:8 }}><strong>{t.subject || t.title || "Support request"}</strong><span style={pill}>{t.priority || "normal"}</span></div><p style={{ margin:"6px 0", color:"#64748b", fontSize:12 }}>{t.tenant_name || t.business_name || t.tenant_id || "Tenant"} · {t.status || "new"}</p><p style={{ margin:0, fontSize:13, whiteSpace:"pre-wrap" }}>{t.body || t.description || ""}</p><p style={{ margin:"7px 0 0", color:"#94a3b8", fontSize:11 }}>{t.created_at ? new Date(t.created_at).toLocaleString() : ""}</p></div>)}
        <p style={{ color:"#94a3b8", fontSize:11, marginTop:12 }}>Reply and update ticket status from platform Tickets.</p><a href="/platform/tickets" style={linkStyle}>Open ticket management →</a>
      </section>
      <section style={panel}><SectionHeading title="Recent platform messages" subtitle="Messages sent by Super Admin to tenant owners." />
        {messages.length === 0 ? <Empty text="No platform messages yet." /> : messages.slice(0,30).map((m,i) => <div key={m.id || i} style={listRow}><strong>{m.subject || "Platform message"}</strong><p style={{ margin:"6px 0", color:"#64748b", fontSize:12 }}>Tenant: {m.tenant_name || m.tenant_id || "—"} · {m.email_status || m.status || "recorded"}</p><p style={{ margin:0, fontSize:13, whiteSpace:"pre-wrap" }}>{m.body || m.message || ""}</p><p style={{ margin:"7px 0 0", color:"#94a3b8", fontSize:11 }}>{m.created_at ? new Date(m.created_at).toLocaleString() : ""}</p></div>)}
      </section>
    </div>}
    {!loading && tab === "campaigns" && <section style={{ ...panel, maxWidth:1000 }}>
      <SectionHeading title="Send a promotional campaign" subtitle="Use your platform-owned provider, not a tenant's connection." />
      <div style={{ padding:12, background:"#fff8e8", color:"#8a5a10", border:"1px solid #f3dfb4", borderRadius:10, fontSize:12, margin:"16px 0" }}>Only send to people who have explicitly opted in to the selected channel. These sample recipients are examples; replace them with your own consented list before sending.</div>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(240px,1fr))", gap:14 }}>
        <label style={labelStyle}>Campaign name<input value={campaignName} onChange={e=>setCampaignName(e.target.value)} style={fieldStyle}/></label>
        <label style={labelStyle}>Channel<select value={channel} onChange={e=>setChannel(e.target.value as Channel)} style={fieldStyle}><option value="whatsapp">WhatsApp</option><option value="email">Email</option></select></label>
      </div>
      {channel === "email" && <label style={{ ...labelStyle, display:"block", marginTop:13 }}>Email subject<input value={subject} onChange={e=>setSubject(e.target.value)} style={fieldStyle}/></label>}
      {channel === "whatsapp" && <label style={{ ...labelStyle, display:"block", marginTop:13 }}>WhatsApp approved template name<input value={templateName} onChange={e=>setTemplateName(e.target.value)} style={fieldStyle}/><small style={{ color:"#8793a5", fontWeight:400 }}>For Meta Cloud API, this must match an approved marketing template. Default: re_engagement.</small></label>}
      <label style={{ ...labelStyle, display:"block", marginTop:13 }}>Message<textarea value={body} onChange={e=>setBody(e.target.value)} rows={5} style={{ ...fieldStyle, resize:"vertical", lineHeight:1.5 }}/><small style={{ color:"#8793a5", fontWeight:400 }}>Personalisation: {"{{name}}"} and {"{{company}}"}</small></label>
      <label style={{ ...labelStyle, display:"block", marginTop:13 }}>Recipient list (JSON)<textarea value={contactsJson} onChange={e=>setContactsJson(e.target.value)} rows={10} spellCheck={false} style={{ ...fieldStyle, resize:"vertical", fontFamily:"monospace", fontSize:12, lineHeight:1.45 }}/></label>
      <div style={{display:"flex",gap:10,flexWrap:"wrap",alignItems:"center",marginTop:10}}>
        <label style={{...secondaryButton,display:"inline-block"}}>Import CSV<input type="file" accept=".csv,.txt" style={{display:"none"}} onChange={async e=>{const file=e.target.files?.[0];if(!file)return;const text=await file.text();const lines=text.split(/\\r?\\n/).filter(Boolean);if(lines.length<2){setError("CSV needs a header row and at least one contact.");return;}const headers=lines[0].split(",").map(x=>x.trim().toLowerCase().replace(/^"|"$/g,""));const contacts=lines.slice(1).map(line=>{const vals=line.match(/(?:[^,"]|"[^"]*")+/g)?.map(x=>x.trim().replace(/^"|"$/g,"").replace(/""/g,'"'))||[];const row:any={};headers.forEach((h,i)=>row[h]=vals[i]||"");return {name:row.name||"",email:row.email||"",phone:row.phone||"",email_opt_in:["true","yes","1"].includes(String(row.email_opt_in).toLowerCase()),whatsapp_opt_in:["true","yes","1"].includes(String(row.whatsapp_opt_in).toLowerCase())};});setContactsJson(JSON.stringify(contacts,null,2));e.currentTarget.value="";}}> </label>
        <button type="button" style={secondaryButton} onClick={()=>{const csv="name,email,phone,email_opt_in,whatsapp_opt_in\\nExample Contact,contact@example.com,+919876543210,false,false\\n";const blob=new Blob([csv],{type:"text/csv;charset=utf-8"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="ai-growth-os-campaign-contacts-template.csv";a.click();URL.revokeObjectURL(url);}}>Download CSV template</button>
        <span style={{color:"#8793a5",fontSize:11}}>Columns: name, email, phone, email_opt_in, whatsapp_opt_in</span>
      </div>
      <p style={{ color:"#7b8798", fontSize:12 }}>Maximum {status?.campaign_contact_limit || 500} contacts per send. Each contact must have the selected channel's explicit opt-in set to true.</p>
      <button onClick={() => void sendCampaign()} disabled={sending || !campaignName.trim() || !body.trim()} style={primaryButton}>{sending ? "Sending campaign…" : "Send campaign"}</button>
      {campaignResult && <div style={{ marginTop:18, padding:15, border:"1px solid #b9e5d3", background:"#f0fbf6", borderRadius:10 }}><strong>Campaign result: {campaignResult.campaign}</strong><div style={{ display:"flex", gap:18, flexWrap:"wrap", marginTop:8, fontSize:13 }}><span>Attempted: <b>{campaignResult.attempted}</b></span><span>Sent: <b>{campaignResult.sent}</b></span><span>Failed: <b>{campaignResult.failed}</b></span><span>Skipped: <b>{campaignResult.skipped}</b></span></div>{campaignResult.results?.length > 0 && <div style={{ marginTop:12, maxHeight:220, overflow:"auto" }}>{campaignResult.results.map((r:any,i:number)=><div key={i} style={{ fontSize:12, padding:"5px 0", borderTop:"1px solid #d8efe4" }}>{r.recipient} — {r.status}{r.error ? " · "+r.error : ""}</div>)}</div>}</div>}
    </section>}
    {!loading && tab === "settings" && <section style={{ ...panel, maxWidth:900 }}>
      <SectionHeading title="Platform-owned channel status" subtitle="Provider secrets are never shown in the browser. Tenant integrations are unchanged."/>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(250px,1fr))", gap:14, marginTop:18 }}>
        <ChannelCard title="Platform email" configured={!!status?.email_configured} details={status?.email_configured ? "Sender: "+status.email_from : "Configure RESEND_API_KEY and NOTIFICATION_FROM_EMAIL in the API service environment."}/>
        <ChannelCard title="Platform WhatsApp" configured={!!status?.whatsapp_configured} details={status?.whatsapp_configured ? "Provider: "+status.whatsapp_provider : "Configure the notification WhatsApp provider and credentials in the API service environment."}/>
      </div>
      <div style={{ marginTop:18, padding:14, border:"1px solid #e3e8f0", borderRadius:10, color:"#64748b", fontSize:12, lineHeight:1.6 }}><b style={{ color:"#334155" }}>Configuration safety:</b> update provider secrets in the secured deployment environment. This page does not read or change tenant credentials.</div>
    </section>}
  </div>;
}
function safeItems(d:any):any[] { return Array.isArray(d) ? d : Array.isArray(d?.items) ? d.items : []; }
function Stat({label,value,detail,good}:{label:string;value:string|number;detail:string;good?:boolean}) { return <div style={{ background:"#fff", border:"1px solid #e5eaf1", borderRadius:13, padding:16 }}><div style={{ color:"#8793a5", fontSize:10, fontWeight:800, letterSpacing:".08em", textTransform:"uppercase" }}>{label}</div><div style={{ color:good===undefined?"#17213a":good?"#14856b":"#b45309", fontSize:21, fontWeight:800, marginTop:8 }}>{value}</div><div style={{ color:"#8793a5", fontSize:11, marginTop:5 }}>{detail}</div></div>; }
function SectionHeading({title,subtitle}:{title:string;subtitle:string}) { return <div><h2 style={{ margin:0, color:"#17213a", fontSize:17 }}>{title}</h2><p style={{ margin:"5px 0 0", color:"#8793a5", fontSize:12 }}>{subtitle}</p></div>; }
function Empty({text}:{text:string}) { return <div style={{ padding:22, color:"#94a3b8", background:"#f8fafc", borderRadius:9, fontSize:13, marginTop:12 }}>{text}</div>; }
function ChannelCard({title,configured,details}:{title:string;configured:boolean;details:string}) { return <div style={{ border:"1px solid #e5eaf1", borderRadius:12, padding:16 }}><div style={{ display:"flex", justifyContent:"space-between", gap:10, alignItems:"center" }}><strong>{title}</strong><span style={{ ...pill, color:configured?"#147d5e":"#a16207", background:configured?"#e9f8f1":"#fff6df" }}>{configured?"Configured":"Needs setup"}</span></div><p style={{ color:"#64748b", fontSize:12, lineHeight:1.6, marginBottom:0 }}>{details}</p></div>; }
const panel:React.CSSProperties={background:"#fff",border:"1px solid #e5eaf1",borderRadius:14,padding:18};
const listRow:React.CSSProperties={padding:"13px 0",borderBottom:"1px solid #edf1f5",color:"#263449",fontSize:13};
const pill:React.CSSProperties={display:"inline-block",padding:"4px 8px",borderRadius:30,background:"#eef2f7",color:"#526174",fontSize:10,fontWeight:800,whiteSpace:"nowrap"};
const fieldStyle:React.CSSProperties={display:"block",width:"100%",boxSizing:"border-box",marginTop:6,padding:"10px 11px",border:"1px solid #d8e0ea",borderRadius:9,background:"#fff",color:"#17213a",fontSize:13};
const labelStyle:React.CSSProperties={color:"#344256",fontSize:12,fontWeight:700};
const primaryButton:React.CSSProperties={border:0,borderRadius:9,background:"#176b58",color:"#fff",padding:"11px 17px",fontSize:13,fontWeight:800,cursor:"pointer"};
const secondaryButton:React.CSSProperties={border:"1px solid #d8e0ea",borderRadius:9,background:"#fff",color:"#344256",padding:"10px 13px",fontSize:12,fontWeight:700,cursor:"pointer"};
const linkStyle:React.CSSProperties={display:"inline-block",marginTop:14,color:"#176b58",fontSize:13,fontWeight:700};
function tabStyle(active:boolean):React.CSSProperties{return {border:0,borderBottom:active?"2px solid #176b58":"2px solid transparent",background:"transparent",color:active?"#176b58":"#7b8798",padding:"12px 15px",marginBottom:-1,fontSize:13,fontWeight:800,whiteSpace:"nowrap",cursor:"pointer"};}


function ProviderSetup({token,onError}:{token:string;onError:(s:string)=>void}) {
  const [provider,setProvider]=useState<"openwa"|"meta">("openwa");
  const [baseUrl,setBaseUrl]=useState("");
  const [apiKey,setApiKey]=useState("");
  const [sessionId,setSessionId]=useState("");
  const [accessToken,setAccessToken]=useState("");
  const [phoneId,setPhoneId]=useState("");
  const [activate,setActivate]=useState(true);
  const [active,setActive]=useState("openwa");
  const [configured,setConfigured]=useState<{openwa:boolean;meta:boolean}>({openwa:false,meta:false});
  const [busy,setBusy]=useState(false);
  const [notice,setNotice]=useState("");
  async function load(){if(!token)return;try{const r=await fetch(API+"/api/v1/platform/communications/whatsapp-provider",{headers:{Authorization:"Bearer "+token},cache:"no-store"});if(r.ok){const d=await r.json();setActive(d.active_provider||"openwa");setConfigured(d.configured||{openwa:false,meta:false});}}catch{}}
  useEffect(()=>{void load();},[token]);
  async function save(){setBusy(true);setNotice("");onError("");try{const payload:any={provider,activate};if(provider==="openwa")Object.assign(payload,{base_url:baseUrl,api_key:apiKey,session_id:sessionId});else Object.assign(payload,{access_token:accessToken,phone_number_id:phoneId});const r=await fetch(API+"/api/v1/platform/communications/whatsapp-provider",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token},body:JSON.stringify(payload)});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||"Provider setup failed");setNotice("Credentials validated and saved securely.");setApiKey("");setAccessToken("");await load();}catch(e:any){onError(e.message||"Provider setup failed");}finally{setBusy(false);}}
  const label:React.CSSProperties={display:"block",fontSize:12,fontWeight:700,color:"#344256"};
  const input:React.CSSProperties={display:"block",width:"100%",boxSizing:"border-box",marginTop:6,padding:"10px 11px",border:"1px solid #d8e0ea",borderRadius:9,fontSize:13};
  return <section style={{...panel,marginBottom:20,borderColor:"#dce8e4"}}>
    <div style={{display:"flex",justifyContent:"space-between",gap:12,flexWrap:"wrap",alignItems:"center"}}><div><h2 style={{margin:0,fontSize:17,color:"#17213a"}}>WhatsApp provider setup</h2><p style={{margin:"5px 0 0",fontSize:12,color:"#8793a5"}}>Add credentials, validate, then save. Keys are masked and encrypted on the API.</p></div><span style={pill}>Active: {active}</span></div>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:12,marginTop:15}}>
      <label style={label}>Provider<select value={provider} onChange={e=>setProvider(e.target.value as any)} style={input}><option value="openwa">OpenWA (primary)</option><option value="meta">Meta WhatsApp (alternative)</option></select></label>
      <label style={{...label,display:"flex",alignItems:"center",gap:8,paddingTop:20}}><input type="checkbox" checked={activate} onChange={e=>setActivate(e.target.checked)}/> Make this the active provider</label>
    </div>
    {provider==="openwa"?<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:12,marginTop:12}}>
      <label style={label}>OpenWA server URL<input value={baseUrl} onChange={e=>setBaseUrl(e.target.value)} placeholder="https://your-openwa-server" style={input}/></label>
      <label style={label}>API key<input type="password" value={apiKey} onChange={e=>setApiKey(e.target.value)} autoComplete="new-password" style={input}/></label>
      <label style={label}>Session ID<input value={sessionId} onChange={e=>setSessionId(e.target.value)} style={input}/></label>
    </div>:<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:12,marginTop:12}}>
      <label style={label}>Meta access token<input type="password" value={accessToken} onChange={e=>setAccessToken(e.target.value)} autoComplete="new-password" style={input}/></label>
      <label style={label}>Phone number ID<input value={phoneId} onChange={e=>setPhoneId(e.target.value)} style={input}/></label>
    </div>}
    <div style={{display:"flex",gap:12,alignItems:"center",flexWrap:"wrap",marginTop:14}}><button onClick={()=>void save()} disabled={busy||!token||(provider==="openwa"?(!baseUrl||!apiKey||!sessionId):(!accessToken||!phoneId))} style={primaryButton}>{busy?"Validating…":"Apply & Save"}</button><span style={{fontSize:12,color:"#64748b"}}>OpenWA: {configured.openwa?"saved":"not saved"} · Meta: {configured.meta?"saved":"not saved"}</span></div>
    {notice&&<p role="status" style={{color:"#147d5e",fontSize:12,marginBottom:0}}>{notice}</p>}
  </section>;
}
