"use client";

import { useEffect, useState } from "react";
import { Bot, Phone, Plus, RefreshCw, ShieldCheck, RadioTower } from "lucide-react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const headers = () => ({
  "Content-Type": "application/json",
  Authorization: "Bearer " + (typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : ""),
});

type Agent = { id: string; name: string; status: string; language_codes: string[]; industry_template?: string | null };
type Trunk = { id: string; name: string; provider: string; registrar_host: string; status: string };
type Did = { id: string; e164_number: string; status: string; agent_id?: string | null; trunk_id: string };

export default function AIVoiceWorkspace() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [trunks, setTrunks] = useState<Trunk[]>([]);
  const [dids, setDids] = useState<Did[]>([]);
  const [tab, setTab] = useState<"agents" | "telephony">("agents");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [agentName, setAgentName] = useState("");
  const [industry, setIndustry] = useState("general");
  const [languages, setLanguages] = useState("en,hi,te");
  const [greeting, setGreeting] = useState("");
  const [instructions, setInstructions] = useState("");
  const [trunkName, setTrunkName] = useState("");
  const [provider, setProvider] = useState("sip");
  const [host, setHost] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  async function request(path: string, init?: RequestInit) {
    const response = await fetch(api() + path, { ...init, headers: { ...headers(), ...(init?.headers || {}) }, cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  }

  async function refresh() {
    const [a, t, d] = await Promise.all([
      request("/api/v1/ai-voice/agents"),
      request("/api/v1/ai-voice/sip-trunks"),
      request("/api/v1/ai-voice/dids"),
    ]);
    setAgents(a.items || []); setTrunks(t.items || []); setDids(d.items || []);
  }

  useEffect(() => { refresh().catch((e) => setMessage(e.message)); }, []);

  async function createAgent(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMessage("");
    try {
      await request("/api/v1/ai-voice/agents", { method: "POST", body: JSON.stringify({
        name: agentName, industry_template: industry, language_codes: languages.split(",").map(x => x.trim()).filter(Boolean),
        greeting, operating_instructions: instructions,
      })});
      setAgentName(""); setGreeting(""); setInstructions(""); await refresh(); setMessage("Agent draft created.");
    } catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function publishAgent(id: string) {
    setBusy(true); setMessage("");
    try { await request("/api/v1/ai-voice/agents/" + id, { method: "PATCH", body: JSON.stringify({ status: "published" }) }); await refresh(); setMessage("Agent published."); }
    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function createTrunk(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMessage("");
    try {
      await request("/api/v1/ai-voice/sip-trunks", { method: "POST", body: JSON.stringify({
        name: trunkName, provider, registrar_host: host, auth_username: username, auth_password: password,
      })});
      setTrunkName(""); setHost(""); setUsername(""); setPassword(""); await refresh(); setMessage("SIP trunk saved. Provider registration/provisioning is still pending.");
    } catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function routeDid(didId: string, agentId: string) {
    setBusy(true); setMessage("");
    try { await request("/api/v1/ai-voice/dids/" + didId + "/route", { method: "POST", body: JSON.stringify({ agent_id: agentId || null }) }); await refresh(); setMessage("DID route saved."); }
    catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }

  const card: React.CSSProperties = { background: "#fff", border: "1px solid #e3e8f0", borderRadius: 14, padding: 18 };
  const field: React.CSSProperties = { width: "100%", border: "1px solid #d6deea", borderRadius: 9, padding: "10px 12px", fontSize: 13, background: "#fff" };
  const button: React.CSSProperties = { background: "#273cbd", color: "#fff", borderRadius: 9, padding: "10px 14px", fontSize: 13, fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 7 };

  return <main style={{ padding: "28px 24px", maxWidth: 1180, margin: "0 auto", color: "#17243a" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
      <div><div style={{ color: "#5a64d6", fontWeight: 800, fontSize: 11, letterSpacing: 2 }}>AI VOICE WORKSPACE</div><h1 style={{ fontSize: 28, fontWeight: 800, marginTop: 5 }}>Your voice agents</h1><p style={{ color: "#64748b", fontSize: 13, marginTop: 5 }}>Configure agents, approved knowledge and phone connectivity.</p></div>
      <button onClick={() => refresh().catch(e => setMessage(e.message))} style={{ ...button, background: "#fff", color: "#334155", border: "1px solid #dbe2ec" }}><RefreshCw size={15}/> Refresh</button>
    </header>

    <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
      <button onClick={() => setTab("agents")} style={{ ...button, background: tab === "agents" ? "#273cbd" : "#edf1f8", color: tab === "agents" ? "#fff" : "#334155" }}><Bot size={15}/> Agents</button>
      <button onClick={() => setTab("telephony")} style={{ ...button, background: tab === "telephony" ? "#273cbd" : "#edf1f8", color: tab === "telephony" ? "#fff" : "#334155" }}><RadioTower size={15}/> SIP & DID</button>
    </div>
    {message && <p role="status" style={{ background: "#eef2ff", borderRadius: 9, padding: 11, marginBottom: 16, fontSize: 13 }}>{message}</p>}

    {tab === "agents" ? <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(300px,0.85fr)", gap: 18 }}>
      <section style={card}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 14 }}>Configured agents ({agents.length})</h2>
        {agents.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No agents yet. Create your first agent.</p>}
        <div style={{ display: "grid", gap: 10 }}>{agents.map(agent => <article key={agent.id} style={{ border: "1px solid #e7ebf2", borderRadius: 11, padding: 13, display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
          <div><strong style={{ fontSize: 14 }}>{agent.name}</strong><div style={{ color: "#64748b", fontSize: 12, marginTop: 4 }}>{agent.industry_template || "General"} · {(agent.language_codes || []).join(", ")}</div><span style={{ display: "inline-block", marginTop: 7, fontSize: 10, padding: "3px 8px", borderRadius: 20, background: agent.status === "published" ? "#e6f7ee" : "#fff4db", color: agent.status === "published" ? "#187747" : "#8a5a00" }}>{agent.status}</span></div>
          {agent.status !== "published" && <button disabled={busy} onClick={() => publishAgent(agent.id)} style={{ ...button, padding: "8px 10px" }}>Publish</button>}
        </article>)}</div>
      </section>
      <form onSubmit={createAgent} style={card}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 14 }}>Create an agent</h2>
        <div style={{ display: "grid", gap: 10 }}>
          <input required value={agentName} onChange={e => setAgentName(e.target.value)} placeholder="Agent name" style={field}/>
          <select value={industry} onChange={e => setIndustry(e.target.value)} style={field}><option value="general">General business</option><option value="clinic">Clinic</option><option value="restaurant">Restaurant</option><option value="salon">Salon</option><option value="real-estate">Real estate</option><option value="education">Education</option><option value="gym">Gym / Fitness</option><option value="hotel">Hotel / Hospitality</option></select>
          <input value={languages} onChange={e => setLanguages(e.target.value)} placeholder="Languages: en,hi,te,ta..." style={field}/>
          <textarea value={greeting} onChange={e => setGreeting(e.target.value)} placeholder="Greeting message" rows={2} style={field}/>
          <textarea value={instructions} onChange={e => setInstructions(e.target.value)} placeholder="Agent operating instructions (tenant-specific)" rows={5} style={field}/>
          <button disabled={busy} type="submit" style={button}><Plus size={15}/> Create draft agent</button>
        </div>
      </form>
    </div> : <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(300px,0.85fr)", gap: 18 }}>
      <section style={card}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 14 }}>SIP trunks ({trunks.length})</h2>
        {trunks.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No tenant SIP trunks configured.</p>}
        {trunks.map(t => <article key={t.id} style={{ borderBottom: "1px solid #edf0f5", padding: "11px 0" }}><strong>{t.name}</strong><div style={{ fontSize: 12, color: "#64748b" }}>{t.provider} · {t.registrar_host} · {t.status}</div></article>)}
        <h2 style={{ fontSize: 17, fontWeight: 800, margin: "24px 0 12px" }}>Assigned DID numbers ({dids.length})</h2>
        {dids.map(d => <article key={d.id} style={{ borderBottom: "1px solid #edf0f5", padding: "11px 0" }}>
          <strong>{d.e164_number}</strong><div style={{ color: "#64748b", fontSize: 12, margin: "6px 0" }}>Status: {d.status}</div>
          <select value={d.agent_id || ""} onChange={e => routeDid(d.id, e.target.value)} style={field}><option value="">No agent assigned</option>{agents.filter(a => a.status === "published").map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
        </article>)}
      </section>
      <form onSubmit={createTrunk} style={card}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 14 }}>Connect a SIP trunk</h2>
        <p style={{ fontSize: 12, color: "#64748b", marginBottom: 12 }}>Credentials are encrypted before storage. Saving a trunk does not mean the provider is registered or calls are live.</p>
        <div style={{ display: "grid", gap: 10 }}>
          <input required value={trunkName} onChange={e => setTrunkName(e.target.value)} placeholder="Trunk name" style={field}/>
          <input required value={provider} onChange={e => setProvider(e.target.value)} placeholder="Provider (e.g. Airtel, Tata, Exotel)" style={field}/>
          <input required value={host} onChange={e => setHost(e.target.value)} placeholder="SIP registrar / proxy host" style={field}/>
          <input value={username} onChange={e => setUsername(e.target.value)} placeholder="SIP username" style={field}/>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="SIP password" style={field}/>
          <button disabled={busy} type="submit" style={button}><ShieldCheck size={15}/> Save encrypted trunk config</button>
        </div>
      </form>
    </div>}
    <p style={{ color: "#64748b", fontSize: 11, marginTop: 22 }}>Agent publication currently saves tenant configuration. Live SIP registration, DID provisioning, test-call routing and provider health checks remain separate activation gates.</p>
  </main>;
}
