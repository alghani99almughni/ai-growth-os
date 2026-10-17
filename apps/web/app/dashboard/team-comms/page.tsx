"use client";
import { FormEvent, useCallback, useEffect, useState } from "react";

type Member = { id: string; name: string; email?: string; role?: string };
type Message = { id: string; sender_id: string; sender_name: string; message: string; created_at: string };

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export default function TeamCommsPage() {
  const [token, setToken] = useState("");
  const [members, setMembers] = useState<Member[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [myId, setMyId] = useState("");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");

  const headers = { Authorization: "Bearer " + token, "Content-Type": "application/json" };
  const load = useCallback(async () => {
    if (!token) return;
    try {
      const base = API + "/api/v1/team-comms";
      const results = await Promise.all([
        fetch(base + "/users", { headers: { Authorization: "Bearer " + token }, cache: "no-store" }),
        fetch(base + "/messages?room=team&limit=200", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
      ]);
      const data = await Promise.all(results.map((r) => r.json().catch(() => ({}))));
      if (!results[0].ok) throw new Error(data[0].detail || "Unable to load team members.");
      if (!results[1].ok) throw new Error(data[1].detail || "Unable to load messages.");
      setMembers(Array.isArray(data[0]) ? data[0] : []);
      setMessages(Array.isArray(data[1]) ? data[1] : []);
      setError("");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not load team communications."); }
  }, [token]);

  useEffect(() => {
    const saved = localStorage.getItem("ago_access_token") || "";
    setToken(saved);
    try {
      const payload = saved.split(".")[1];
      if (payload) setMyId(String(JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))).sub || ""));
    } catch {}
    if (!saved) window.location.href = "/login";
  }, []);

  useEffect(() => {
    if (!token) return;
    void load();
    const id = window.setInterval(() => void load(), 8000);
    return () => window.clearInterval(id);
  }, [token, load]);

  async function send(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true); setError("");
    try {
      const r = await fetch(API + "/api/v1/team-comms/messages", {
        method: "POST", headers, body: JSON.stringify({ message: text, room: "team", recipient_id: null })
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(data.detail || "Message could not be sent.");
      setDraft("");
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : "Message could not be sent."); }
    finally { setBusy(false); }
  }

  async function exportCsv() {
    try {
      const r = await fetch(API + "/api/v1/team-comms/export.csv", { headers: { Authorization: "Bearer " + token }, cache: "no-store" });
      if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || "Export permission required."); }
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url; a.download = "team-chat-export.csv"; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch (e) { setError(e instanceof Error ? e.message : "Export failed."); }
  }

  const filtered = members.filter((m) => [m.name, m.email || "", m.role || ""].some((s) => s.toLowerCase().includes(query.toLowerCase())));
  const panel: React.CSSProperties = { background: "#fff", border: "1px solid #e3e8f0", borderRadius: 14 };
  const btn: React.CSSProperties = { border: "1px solid #d8e0eb", borderRadius: 9, padding: "9px 13px", background: "#fff", cursor: "pointer", fontWeight: 650 };
  if (!token) return <div style={{ padding: 40 }}>Checking sign-in…</div>;

  return <main style={{ maxWidth: 1300, margin: "0 auto", color: "#17213a" }}>
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 14, flexWrap: "wrap", marginBottom: 22 }}>
      <div><div style={{ color: "#64748b", fontSize: 12, textTransform: "uppercase", letterSpacing: ".08em", fontWeight: 700 }}>Workspace collaboration</div><h1 style={{ margin: "7px 0", fontSize: 30 }}>Team Communications</h1><p style={{ margin: 0, color: "#64748b" }}>Shared chat for active members in your tenant workspace.</p></div>
      <div style={{ display: "flex", gap: 8 }}><button style={btn} onClick={() => void load()}>Refresh</button><button style={btn} onClick={() => void exportCsv()}>Export CSV</button></div>
    </header>
    {error && <div role="alert" style={{ padding: 12, background: "#fff1f1", color: "#9f2525", borderRadius: 9, marginBottom: 14 }}>{error}</div>}
    <div className="team-layout" style={{ display: "grid", gridTemplateColumns: "minmax(220px, 280px) minmax(0, 1fr)", gap: 16 }}>
      <aside style={{ ...panel, padding: 16 }}>
        <strong>Workspace members</strong><p style={{ color: "#64748b", fontSize: 12, marginTop: 5 }}>{members.length} active member(s)</p>
        <input aria-label="Search members" placeholder="Search people…" value={query} onChange={(e) => setQuery(e.target.value)} style={{ width: "100%", boxSizing: "border-box", padding: 10, border: "1px solid #d8e0eb", borderRadius: 8, marginBottom: 12 }} />
        {filtered.map((m) => <div key={m.id} style={{ display: "flex", gap: 10, alignItems: "center", padding: "10px 3px", borderBottom: "1px solid #f0f2f6" }}><span style={{ display: "grid", placeItems: "center", width: 34, height: 34, borderRadius: 11, background: "#e8edff", color: "#354ac4", fontWeight: 800 }}>{(m.name || "?").slice(0, 1).toUpperCase()}</span><div><div style={{ fontSize: 13, fontWeight: 700 }}>{m.name}{m.id === myId ? " (you)" : ""}</div><div style={{ color: "#64748b", fontSize: 11 }}>{(m.role || "member").replace(/_/g, " ")}</div></div></div>)}
      </aside>
      <section style={{ ...panel, minHeight: 590, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: 16, borderBottom: "1px solid #edf0f5" }}><strong># Team room</strong><div style={{ color: "#64748b", fontSize: 12, marginTop: 4 }}>Messages are shared with active members of this tenant.</div></div>
        <div aria-live="polite" style={{ flex: 1, minHeight: 390, maxHeight: "62vh", overflowY: "auto", padding: 18, background: "#fbfcfe" }}>
          {messages.length === 0 && <p style={{ textAlign: "center", color: "#64748b", padding: 50 }}>No messages yet. Start the conversation below.</p>}
          {messages.map((m) => { const mine = m.sender_id === myId; return <div key={m.id} style={{ display: "flex", justifyContent: mine ? "flex-end" : "flex-start", marginBottom: 14 }}><div style={{ maxWidth: "80%" }}><div style={{ fontSize: 11, color: "#64748b", marginBottom: 4, textAlign: mine ? "right" : "left" }}>{mine ? "You" : m.sender_name} · {new Date(m.created_at).toLocaleString()}</div><div style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", padding: "11px 13px", background: mine ? "#e9edff" : "#f0f3f8", borderRadius: 12, fontSize: 14 }}>{m.message}</div></div></div>; })}
        </div>
        <form onSubmit={send} style={{ padding: 14, borderTop: "1px solid #edf0f5", display: "flex", gap: 10, alignItems: "flex-end" }}>
          <textarea aria-label="Message" rows={2} maxLength={10000} placeholder="Message your team… (Enter to send)" value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); e.currentTarget.form?.requestSubmit(); } }} style={{ flex: 1, resize: "vertical", minHeight: 45, padding: 11, border: "1px solid #d8e0eb", borderRadius: 9, font: "inherit" }} />
          <button type="submit" disabled={busy || !draft.trim()} style={{ ...btn, color: "#fff", background: busy || !draft.trim() ? "#aab4c7" : "#293dbd", border: 0 }}>{busy ? "Sending…" : "Send"}</button>
        </form>
        <div style={{ padding: "0 16px 12px", color: "#64748b", fontSize: 11 }}>Auto-refreshes every 8 seconds. CSV export is subject to role permissions.</div>
      </section>
    </div>
    <style jsx>{".team-layout { grid-template-columns: minmax(220px, 280px) minmax(0, 1fr); } @media(max-width: 780px) { .team-layout { grid-template-columns: 1fr; } }"}</style>
  </main>;
}
