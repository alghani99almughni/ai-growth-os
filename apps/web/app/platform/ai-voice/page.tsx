"use client";

import { useEffect, useState } from "react";
import { Building2, Phone, RefreshCw, RadioTower, ShieldCheck } from "lucide-react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const headers = () => ({ "Content-Type": "application/json", Authorization: "Bearer " + (typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : "") });

export default function PlatformAIVoice() {
  const [trunks, setTrunks] = useState<any[]>([]);
  const [dids, setDids] = useState<any[]>([]);
  const [tenants, setTenants] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [trunkId, setTrunkId] = useState("");
  const [number, setNumber] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [platformTrunkName, setPlatformTrunkName] = useState("");
  const [platformProvider, setPlatformProvider] = useState("sip");
  const [platformHost, setPlatformHost] = useState("");
  const [platformUsername, setPlatformUsername] = useState("");
  const [platformPassword, setPlatformPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function req(path: string, init?: RequestInit) {
    const r = await fetch(api() + path, { ...init, headers: { ...headers(), ...(init?.headers || {}) }, cache: "no-store" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "Request failed");
    return d;
  }

  async function refresh() {
    const [t, d, ts] = await Promise.all([
      req("/api/v1/ai-voice/platform/sip-trunks"),
      req("/api/v1/ai-voice/platform/dids"),
      req("/api/v1/platform/tenants"),
    ]);
    setTrunks(t.items || []); setDids(d.items || []); setTenants(ts.items || ts.tenants || []);
    if (!trunkId && t.items?.length) setTrunkId(t.items[0].id);
  }

  useEffect(() => { refresh().catch(e => setMessage(e.message)); }, []);

  async function createPlatformTrunk(e: React.FormEvent) {\n    e.preventDefault(); setBusy(true); setMessage("");\n    try { await req("/api/v1/ai-voice/platform/sip-trunks", { method: "POST", body: JSON.stringify({ name: platformTrunkName, provider: platformProvider, registrar_host: platformHost, auth_username: platformUsername, auth_password: platformPassword }) }); setPlatformTrunkName(""); setPlatformHost(""); setPlatformUsername(""); setPlatformPassword(""); await refresh(); setMessage("Platform SIP trunk saved with encrypted credentials. Registration remains pending until a telephony adapter is connected."); }\n    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }\n  }\n\n  async function createDid(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMessage("");
    try { await req("/api/v1/ai-voice/platform/dids", { method: "POST", body: JSON.stringify({ e164_number: number, trunk_id: trunkId }) }); setNumber(""); await refresh(); setMessage("DID added to platform inventory."); }
    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function assignDid(did: any) {
    setBusy(true); setMessage("");
    try { await req("/api/v1/ai-voice/platform/dids/" + did.id + "/assign", { method: "POST", body: JSON.stringify({ tenant_id: tenantId, agent_id: agentId || null }) }); await refresh(); setMessage("DID assignment saved."); }
    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }

  useEffect(() => {
    if (!tenantId) { setAgents([]); return; }
    req("/api/v1/ai-voice/platform/tenants/" + encodeURIComponent(tenantId) + "/agents").then(d => setAgents(d.items || [])).catch(() => setAgents([]));
  }, [tenantId]);

  const panel: React.CSSProperties = { background: "#fff", border: "1px solid #e3e8f0", borderRadius: 14, padding: 18 };
  const input: React.CSSProperties = { width: "100%", border: "1px solid #d6deea", borderRadius: 9, padding: "10px 12px", fontSize: 13 };
  const button: React.CSSProperties = { background: "#273cbd", color: "#fff", borderRadius: 9, padding: "10px 14px", fontSize: 13, fontWeight: 700 };

  return <main style={{ padding: "28px 24px", maxWidth: 1180, margin: "0 auto", color: "#17243a" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24, flexWrap: "wrap", gap: 12 }}>
      <div><div style={{ color: "#5a64d6", fontWeight: 800, fontSize: 11, letterSpacing: 2 }}>PLATFORM OPERATIONS</div><h1 style={{ fontSize: 28, fontWeight: 800, marginTop: 5 }}>AI Voice control</h1><p style={{ color: "#64748b", fontSize: 13, marginTop: 5 }}>Manage platform SIP trunks, DID inventory and tenant assignments.</p></div>
      <button onClick={() => refresh().catch(e => setMessage(e.message))} style={{ ...button, background: "#fff", color: "#334155", border: "1px solid #dbe2ec", display: "inline-flex", alignItems: "center", gap: 8 }}><RefreshCw size={15}/> Refresh</button>
    </header>
    {message && <p role="status" style={{ background: "#eef2ff", borderRadius: 9, padding: 11, marginBottom: 16, fontSize: 13 }}>{message}</p>}
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: 12, marginBottom: 18 }}>
      {[["SIP trunks", trunks.length, RadioTower], ["DID numbers", dids.length, Phone], ["Tenants", tenants.length, Building2]].map(([label, value, Icon]: any) => <div key={label} style={panel}><div style={{ color: "#64748b", fontSize: 12 }}>{label}</div><div style={{ fontSize: 25, fontWeight: 800, marginTop: 5 }}>{value}</div></div>)}
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(300px,0.8fr)", gap: 18 }}>
      <section style={panel}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 12 }}>DID inventory</h2>
        {dids.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No DID numbers in platform inventory.</p>}
        {dids.map(d => <article key={d.id} style={{ padding: "13px 0", borderBottom: "1px solid #edf0f5" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}><strong>{d.e164_number}</strong><span style={{ fontSize: 11, color: "#64748b" }}>{d.status}</span></div>
          <div style={{ color: "#64748b", fontSize: 11, margin: "5px 0 10px" }}>Trunk: {trunks.find(t => t.id === d.trunk_id)?.name || d.trunk_id}</div>
          {!d.tenant_id ? <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto", gap: 7 }}>
            <select value={tenantId} onChange={e => setTenantId(e.target.value)} style={input}><option value="">Select tenant</option>{tenants.map(t => <option key={t.id} value={t.id}>{t.name || t.business_name}</option>)}</select>
            <select value={agentId} onChange={e => setAgentId(e.target.value)} style={input}><option value="">Select agent (optional)</option>{agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
            <button disabled={busy || !tenantId} onClick={() => assignDid(d)} style={button}>Assign</button>
          </div> : <div style={{ fontSize: 12, color: "#16734b" }}>Assigned to tenant {d.tenant_id} · Agent {d.agent_id || "not selected"}</div>}
        </article>)}
      </section>
      <div style={{ display: "grid", gap: 18, alignContent: "start" }}>
        <section style={panel}>
          <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 12 }}>Platform SIP trunks</h2>
          {trunks.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No platform-owned SIP trunks yet. Add them through the secure platform provisioning workflow.</p>}
          {trunks.map(t => <div key={t.id} style={{ padding: "10px 0", borderBottom: "1px solid #edf0f5" }}><strong style={{ fontSize: 13 }}>{t.name}</strong><div style={{ color: "#64748b", fontSize: 11 }}>{t.provider} · {t.registrar_host} · {t.status}</div></div>)}
        </section>
        <form onSubmit={createPlatformTrunk} style={panel}>
          <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 12 }}>Add platform SIP trunk</h2>
          <div style={{ display: "grid", gap: 9 }}>
            <input required value={platformTrunkName} onChange={e => setPlatformTrunkName(e.target.value)} placeholder="Trunk name" style={input}/>
            <input required value={platformProvider} onChange={e => setPlatformProvider(e.target.value)} placeholder="Provider" style={input}/>
            <input required value={platformHost} onChange={e => setPlatformHost(e.target.value)} placeholder="SIP registrar / proxy host" style={input}/>
            <input value={platformUsername} onChange={e => setPlatformUsername(e.target.value)} placeholder="SIP username" style={input}/>
            <input type="password" value={platformPassword} onChange={e => setPlatformPassword(e.target.value)} placeholder="SIP password" style={input}/>
            <button disabled={busy} style={button}>Save platform trunk</button>
          </div>
        </form>
        <form onSubmit={createDid} style={panel}>
          <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 12 }}>Add DID to inventory</h2>
          <div style={{ display: "grid", gap: 10 }}>
            <select required value={trunkId} onChange={e => setTrunkId(e.target.value)} style={input}><option value="">Select trunk</option>{trunks.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}</select>
            <input required value={number} onChange={e => setNumber(e.target.value)} placeholder="+919876543210" style={input}/>
            <button disabled={busy || !trunkId} style={button}><ShieldCheck size={14} style={{ display: "inline", marginRight: 6 }}/>Add inventory number</button>
          </div>
        </form>
      </div>
    </div>
    <p style={{ color: "#64748b", fontSize: 11, marginTop: 22 }}>This page manages the control-plane records. Provider API provisioning, SIP registration/health checks and live DID routing are not enabled until a telephony edge/provider adapter is configured.</p>
  </main>;
}
