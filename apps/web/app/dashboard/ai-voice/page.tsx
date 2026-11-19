"use client";

import { useEffect, useState } from "react";
import { Bot, Plus, RefreshCw, Sparkles, CreditCard, CheckCircle2 } from "lucide-react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const headers = () => ({
  "Content-Type": "application/json",
  Authorization: "Bearer " + (typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : ""),
});

type Agent = { id: string; name: string; status: string; language_codes: string[]; industry_template?: string | null; voice_provider?: string; voice_profile?: string | null };

export default function AIVoiceWorkspace() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tab, setTab] = useState<"free" | "paid">("free");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [agentName, setAgentName] = useState("");
  const [industry, setIndustry] = useState("general");
  const [languages, setLanguages] = useState("en,hi,te");
  const [greeting, setGreeting] = useState("");
  const [instructions, setInstructions] = useState("");
  const [selectedAgent, setSelectedAgent] = useState("");
  const [paidProvider, setPaidProvider] = useState("openai");
  const [tenantId, setTenantId] = useState("");
  const [lastMinuteWindow, setLastMinuteWindow] = useState(30);

  async function request(path: string, init?: RequestInit) {
    const response = await fetch(api() + path, { ...init, headers: { ...headers(), ...(init?.headers || {}) }, cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "Request failed");
    return data;
  }

  async function refresh() {
    const a = await request("/api/v1/ai-voice/agents");
    const list: Agent[] = a.items || [];
    setAgents(list);
    if (!selectedAgent && list.length) {
      setSelectedAgent(list[0].id);
      const provider = list[0].voice_provider || "openai";
      setPaidProvider(["openai", "gemini", "deepgram", "paid_custom"].includes(provider) ? provider : "openai");
    }
  }

  useEffect(() => {
    refresh().catch((e) => setMessage(e.message));
    try {
      const tenant = JSON.parse(localStorage.getItem("ago_tenant") || "{}");
      if (tenant.id) {
        setTenantId(tenant.id);
        request("/api/v1/tenants/" + tenant.id + "/voice/booking-policy")
          .then((p) => setLastMinuteWindow(p.last_minute_window_minutes === 15 ? 15 : 30))
          .catch((e) => setMessage(e.message));
      }
    } catch { setMessage("Unable to load the active tenant context."); }
  }, []);

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

  async function saveBookingPolicy() {
    if (!tenantId) return;
    setBusy(true); setMessage("");
    try {
      await request("/api/v1/tenants/" + tenantId + "/voice/booking-policy", {
        method: "PUT",
        body: JSON.stringify({ last_minute_window_minutes: lastMinuteWindow }),
      });
      setMessage("Voice booking policy saved for this business.");
    } catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function savePaidProvider() {
    if (!selectedAgent) return;
    setBusy(true); setMessage("");
    try {
      await request("/api/v1/ai-voice/agents/" + selectedAgent, { method: "PATCH", body: JSON.stringify({ voice_provider: paidProvider }) });
      await refresh(); setMessage("Paid provider preference saved for this agent. Provider credentials and runtime activation are controlled separately by the platform.");
    } catch (e: any) { setMessage(e.message); } finally { setBusy(false); }
  }

  const card: React.CSSProperties = { background: "#fff", border: "1px solid #e3e8f0", borderRadius: 14, padding: 18 };
  const field: React.CSSProperties = { width: "100%", border: "1px solid #d6deea", borderRadius: 9, padding: "10px 12px", fontSize: 13, background: "#fff" };
  const button: React.CSSProperties = { background: "#273cbd", color: "#fff", borderRadius: 9, padding: "10px 14px", fontSize: 13, fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 7 };

  return <main style={{ padding: "28px 24px", maxWidth: 1180, margin: "0 auto", color: "#17243a" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
      <div><div style={{ color: "#5a64d6", fontWeight: 800, fontSize: 11, letterSpacing: 2 }}>AI VOICE WORKSPACE</div><h1 style={{ fontSize: 28, fontWeight: 800, marginTop: 5 }}>AI Voice</h1><p style={{ color: "#64748b", fontSize: 13, marginTop: 5 }}>Choose the free self-hosted engine or an optional paid provider for your voice agents.</p></div>
      <button onClick={() => refresh().catch(e => setMessage(e.message))} style={{ ...button, background: "#fff", color: "#334155", border: "1px solid #dbe2ec" }}><RefreshCw size={15}/> Refresh</button>
    </header>

    <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
      <button onClick={() => setTab("free")} style={{ ...button, background: tab === "free" ? "#273cbd" : "#edf1f8", color: tab === "free" ? "#fff" : "#334155" }}><Sparkles size={15}/> Free</button>
      <button onClick={() => setTab("paid")} style={{ ...button, background: tab === "paid" ? "#273cbd" : "#edf1f8", color: tab === "paid" ? "#fff" : "#334155" }}><CreditCard size={15}/> Paid</button>
    </div>
    {message && <p role="status" style={{ background: "#eef2ff", borderRadius: 9, padding: 11, marginBottom: 16, fontSize: 13 }}>{message}</p>}

    <section style={{ ...card, marginBottom: 18 }}>
      <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 7 }}>Booking & human handoff policy</h2>
      <p style={{ color: "#64748b", fontSize: 13, lineHeight: 1.6, marginBottom: 12 }}>
        When a call begins close to closing time, the agent will not auto-confirm a same-day booking.
        It will offer the next available slot. A customer insisting on today is routed to the team;
        if nobody is available, a callback request is recorded.
      </p>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <label htmlFor="last-minute-window" style={{ fontSize: 13, fontWeight: 700 }}>Closing-time buffer</label>
        <select id="last-minute-window" value={lastMinuteWindow} onChange={e => setLastMinuteWindow(Number(e.target.value))} style={{ ...field, width: 180 }}>
          <option value={15}>15 minutes</option>
          <option value={30}>30 minutes (default)</option>
        </select>
        <button disabled={busy || !tenantId} onClick={saveBookingPolicy} style={button}>Save booking policy</button>
      </div>
    </section>

    {tab === "free" ? <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(300px,0.85fr)", gap: 18 }}>
      <section style={card}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 8 }}>Free self-hosted voice</h2>
        <p style={{ color: "#64748b", fontSize: 13, lineHeight: 1.6, marginBottom: 14 }}>Zero paid AI API tokens. The platform-managed local engine uses self-hosted speech recognition, language models and speech synthesis. Telephony carrier, hosting and bandwidth charges may still apply.</p>
        <div style={{ display: "grid", gap: 9 }}>
          {["Local speech-to-text (Faster-Whisper)", "Self-hosted language model (Ollama)", "Local text-to-speech (Kokoro)", "Shared Knowledge Brain + your approved business knowledge"].map(x => <div key={x} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}><CheckCircle2 size={16} color="#16834b"/>{x}</div>)}
        </div>
        <div style={{ marginTop: 18, padding: 12, borderRadius: 10, background: "#f5f7fb", fontSize: 12, color: "#64748b" }}>Free engine availability depends on the platform's local inference service being provisioned and healthy.</div>
      </section>
      <form onSubmit={createAgent} style={card}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 14 }}>Create a voice agent</h2>
        <div style={{ display: "grid", gap: 10 }}>
          <input required value={agentName} onChange={e => setAgentName(e.target.value)} placeholder="Agent name" style={field}/>
          <select value={industry} onChange={e => setIndustry(e.target.value)} style={field}><option value="general">General business</option><option value="clinic">Clinic</option><option value="restaurant">Restaurant</option><option value="salon">Salon</option><option value="real-estate">Real estate</option><option value="education">Education</option><option value="gym">Gym / Fitness</option><option value="hotel">Hotel / Hospitality</option></select>
          <input value={languages} onChange={e => setLanguages(e.target.value)} placeholder="Languages: en,hi,te,ta..." style={field}/>
          <textarea value={greeting} onChange={e => setGreeting(e.target.value)} placeholder="Greeting message" rows={2} style={field}/>
          <textarea value={instructions} onChange={e => setInstructions(e.target.value)} placeholder="Agent operating instructions (tenant-specific)" rows={5} style={field}/>
          <button disabled={busy} type="submit" style={button}><Plus size={15}/> Create draft agent</button>
        </div>
      </form>
      <section style={{ ...card, gridColumn: "1 / -1" }}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 12 }}>Your voice agents ({agents.length})</h2>
        {agents.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No agents yet. Create your first agent.</p>}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))", gap: 10 }}>{agents.map(agent => <article key={agent.id} style={{ border: "1px solid #e7ebf2", borderRadius: 11, padding: 13 }}>
          <strong style={{ fontSize: 14 }}>{agent.name}</strong><div style={{ color: "#64748b", fontSize: 12, marginTop: 4 }}>{agent.industry_template || "General"} · {(agent.language_codes || []).join(", ")}</div>
          <span style={{ display: "inline-block", marginTop: 7, fontSize: 10, padding: "3px 8px", borderRadius: 20, background: agent.status === "published" ? "#e6f7ee" : "#fff4db", color: agent.status === "published" ? "#187747" : "#8a5a00" }}>{agent.status}</span>
        </article>)}</div>
      </section>
    </div> : <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(300px,0.8fr)", gap: 18 }}>
      <section style={card}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 8 }}>Optional paid AI providers</h2>
        <p style={{ color: "#64748b", fontSize: 13, lineHeight: 1.6 }}>Use a paid provider when your business chooses to. Charges are based on the provider's usage and are separate from AI Growth OS subscription or telephony costs. Provider credentials, billing limits and availability are managed by Super Admin.</p>
        <div style={{ display: "grid", gap: 9, marginTop: 16 }}>
          {["OpenAI", "Google Gemini", "Deepgram", "Platform-approved custom provider"].map(x => <div key={x} style={{ border: "1px solid #e7ebf2", borderRadius: 10, padding: 12, fontSize: 13 }}>{x}</div>)}
        </div>
      </section>
      <section style={card}>
        <h2 style={{ fontSize: 17, fontWeight: 800, marginBottom: 12 }}>Paid provider preference</h2>
        <label style={{ display: "block", fontSize: 12, color: "#64748b", marginBottom: 6 }}>Voice agent</label>
        <select value={selectedAgent} onChange={e => setSelectedAgent(e.target.value)} style={{ ...field, marginBottom: 12 }}><option value="">Select an agent</option>{agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}</select>
        <label style={{ display: "block", fontSize: 12, color: "#64748b", marginBottom: 6 }}>Preferred paid provider</label>
        <select value={paidProvider} onChange={e => setPaidProvider(e.target.value)} style={{ ...field, marginBottom: 12 }}><option value="openai">OpenAI</option><option value="gemini">Google Gemini</option><option value="deepgram">Deepgram</option><option value="paid_custom">Platform-approved custom</option></select>
        <button disabled={busy || !selectedAgent} onClick={savePaidProvider} style={button}>Save provider preference</button>
        <p style={{ color: "#64748b", fontSize: 11, marginTop: 12 }}>Saving a preference does not activate a paid provider or authorize charges. Provider activation and credentials remain controlled by Super Admin.</p>
      </section>
    </div>}
  </main>;
}
