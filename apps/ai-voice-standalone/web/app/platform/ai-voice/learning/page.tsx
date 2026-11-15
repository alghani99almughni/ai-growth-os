"use client";

import { useEffect, useState } from "react";
import { BookOpen, RefreshCw, Search, CheckCircle2, XCircle, Play } from "lucide-react";

const headers = () => ({
  "Content-Type": "application/json",
  Authorization: "Bearer " + (typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : ""),
});

type Conversation = {
  id: string; tenant_id: string; tenant_name: string; customer_name?: string | null;
  customer_phone?: string | null; source: string; status: string; language: string;
  started_at?: string | null; duration_seconds: number; intent?: string | null;
  summary?: string | null; transcript: string;
};
type Candidate = {
  id: string; tenant_id: string; tenant_name: string; question: string; answer: string;
  language: string; status: string; source: string; times_asked: number;
};

export default function VoiceLearningHub() {
  const [tab, setTab] = useState<"conversations" | "candidates">("conversations");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Conversation | null>(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  async function req(path: string, init?: RequestInit) {
    const r = await fetch(path, { ...init, headers: { ...headers(), ...(init?.headers || {}) }, cache: "no-store" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || "Request failed");
    return d;
  }

  async function refresh() {
    const [calls, learned] = await Promise.all([
      req("/api/v1/ai-voice/platform/conversations?limit=300"),
      req("/api/v1/ai-voice/platform/learning/candidates?status=pending&limit=300"),
    ]);
    setConversations(calls.items || []);
    setCandidates(learned.items || []);
    if (selected) {
      const updated = (calls.items || []).find((x: Conversation) => x.id === selected.id);
      if (updated) setSelected(updated);
    }
  }

  useEffect(() => {
    if (!localStorage.getItem("ago_access_token")) { window.location.replace("/login"); return; }
    refresh().catch(e => setMessage(e.message));
  }, []);

  async function processNow() {
    setBusy(true); setMessage("");
    try {
      const result = await req("/api/v1/ai-voice/platform/learning/process?limit=500", { method: "POST" });
      await refresh();
      setMessage(`Checked ${result.calls_checked} calls · ${result.candidates_created} new knowledge candidates`);
    } catch (e: any) { setMessage(e.message); }
    finally { setBusy(false); }
  }

  async function decide(id: string, action: "approve" | "reject") {
    setBusy(true); setMessage("");
    try {
      await req(`/api/v1/ai-voice/platform/learning/candidates/${id}/${action}`, { method: "POST" });
      await refresh();
      setMessage(action === "approve" ? "Approved and published to the tenant knowledge base." : "Candidate rejected.");
    } catch (e: any) { setMessage(e.message); }
    finally { setBusy(false); }
  }

  const panel: React.CSSProperties = { background: "#fff", border: "1px solid #e3e8f0", borderRadius: 14, padding: 16 };
  const button: React.CSSProperties = { border: "1px solid #d8e0eb", borderRadius: 9, padding: "9px 12px", fontSize: 13, fontWeight: 700, display: "inline-flex", alignItems: "center", gap: 7, background: "#fff", color: "#27364b" };
  const primary: React.CSSProperties = { ...button, background: "#273cbd", borderColor: "#273cbd", color: "#fff" };
  const filtered = conversations.filter(c => [c.tenant_name, c.customer_name, c.customer_phone, c.intent, c.transcript].join(" ").toLowerCase().includes(filter.toLowerCase()));

  return <main style={{ padding: 24, maxWidth: 1380, margin: "0 auto", color: "#17243a" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 20 }}>
      <div><div style={{ color: "#5a64d6", fontWeight: 800, fontSize: 11, letterSpacing: 2 }}>SUPER ADMIN · KNOWLEDGE OPERATIONS</div><h1 style={{ fontSize: 27, fontWeight: 800, marginTop: 5 }}>Conversation Hub & Knowledge Agent</h1><p style={{ color: "#64748b", fontSize: 13, marginTop: 5 }}>Review tenant conversations, extract reusable answers and approve knowledge before it reaches future calls.</p></div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button style={button} onClick={() => refresh().catch(e => setMessage(e.message))}><RefreshCw size={15}/> Refresh</button>
        <button style={primary} disabled={busy} onClick={processNow}><Play size={15}/> Run Knowledge Agent</button>
      </div>
    </header>
    {message && <p role="status" style={{ background: "#eef2ff", borderRadius: 9, padding: 11, marginBottom: 14, fontSize: 13 }}>{message}</p>}
    <div style={{ display: "flex", gap: 8, marginBottom: 14 }}>
      <button style={{ ...button, ...(tab === "conversations" ? primary : {}) }} onClick={() => setTab("conversations")}>Conversation Hub ({conversations.length})</button>
      <button style={{ ...button, ...(tab === "candidates" ? primary : {}) }} onClick={() => setTab("candidates")}>Knowledge Approval ({candidates.length})</button>
    </div>

    {tab === "conversations" ? <div style={{ display: "grid", gridTemplateColumns: "minmax(320px,0.9fr) minmax(380px,1.1fr)", gap: 14 }}>
      <section style={panel}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 12, border: "1px solid #d8e0eb", borderRadius: 9, padding: "8px 10px" }}><Search size={15}/><input value={filter} onChange={e => setFilter(e.target.value)} placeholder="Search tenant, caller, intent or transcript" style={{ border: 0, outline: 0, width: "100%", fontSize: 13 }}/></div>
        <div style={{ display: "grid", gap: 8, maxHeight: 650, overflowY: "auto" }}>
          {filtered.map(c => <button key={c.id} onClick={() => setSelected(c)} style={{ textAlign: "left", border: selected?.id === c.id ? "2px solid #5966d8" : "1px solid #e5eaf1", background: selected?.id === c.id ? "#f5f6ff" : "#fff", borderRadius: 10, padding: 11 }}>
            <strong style={{ fontSize: 13 }}>{c.customer_name || "Unknown caller"} · {c.tenant_name}</strong>
            <div style={{ color: "#64748b", fontSize: 11, marginTop: 4 }}>{c.customer_phone || "No phone"} · {c.language} · {c.status}</div>
            <div style={{ color: "#475569", fontSize: 12, marginTop: 5 }}>{c.intent || c.summary || "No call summary"}</div>
          </button>)}
          {!filtered.length && <p style={{ color: "#64748b", fontSize: 13 }}>No conversations found.</p>}
        </div>
      </section>
      <section style={panel}>
        {selected ? <>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}><div><h2 style={{ fontSize: 17, fontWeight: 800 }}>{selected.customer_name || "Unknown caller"}</h2><p style={{ color: "#64748b", fontSize: 12 }}>{selected.tenant_name} · {selected.customer_phone || "No phone"} · {selected.language}</p></div><span style={{ fontSize: 11, color: "#64748b" }}>{selected.duration_seconds}s</span></div>
          {selected.summary && <p style={{ background: "#f5f7fb", borderRadius: 8, padding: 10, fontSize: 12, marginTop: 12 }}>{selected.summary}</p>}
          <h3 style={{ fontSize: 13, fontWeight: 800, margin: "16px 0 8px" }}>Full transcript</h3>
          <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", background: "#101827", color: "#e5edf7", borderRadius: 10, padding: 14, fontSize: 12, lineHeight: 1.65, maxHeight: 520, overflowY: "auto" }}>{selected.transcript || "No transcript captured for this call."}</pre>
        </> : <div style={{ color: "#64748b", padding: 30, textAlign: "center" }}><BookOpen size={28}/><p style={{ marginTop: 10 }}>Select a conversation to review its transcript.</p></div>}
      </section>
    </div> : <section style={{ display: "grid", gap: 12 }}>
      <p style={{ color: "#64748b", fontSize: 12 }}>The agent extracts customer/AI question-and-answer pairs. Nothing becomes live knowledge until Super Admin approves it.</p>
      {candidates.map(c => <article key={c.id} style={panel}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}><strong style={{ fontSize: 13 }}>{c.tenant_name} · {c.language} · Asked {c.times_asked} time(s)</strong><span style={{ color: "#64748b", fontSize: 11 }}>{c.source}</span></div>
        <div style={{ marginTop: 10, fontSize: 13 }}><strong>Customer question</strong><p style={{ marginTop: 4 }}>{c.question}</p></div>
        <div style={{ marginTop: 10, fontSize: 13 }}><strong>AI response (unverified)</strong><p style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>{c.answer}</p></div>
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button style={primary} disabled={busy} onClick={() => decide(c.id, "approve")}><CheckCircle2 size={15}/> Approve to tenant KB</button>
          <button style={button} disabled={busy} onClick={() => decide(c.id, "reject")}><XCircle size={15}/> Reject</button>
        </div>
      </article>)}
      {!candidates.length && <div style={panel}><p style={{ color: "#64748b", fontSize: 13 }}>No pending knowledge candidates. Run the Knowledge Agent after new calls are completed.</p></div>}
    </section>}
  </main>;
}
