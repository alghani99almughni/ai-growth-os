"use client";
import { useEffect, useState } from "react";

const api = () =>
  String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type ThreadSummary = {
  phone: string;
  contact_name: string | null;
  last_at: string;
  last_body: string;
  last_direction: string;
  message_count: number;
  unread: number;
};

type Msg = { id: string; direction: string; body: string; status: string; created_at: string };
type ThreadDetail = { phone: string; contact_name: string | null; message_count: number; messages: Msg[] };

export default function WhatsAppInboxPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [selected, setSelected] = useState<ThreadDetail | null>(null);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [status, setStatus] = useState("");
  const [query, setQuery] = useState("");

  const h = { Authorization: "Bearer " + token, "Content-Type": "application/json" };

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: h, cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadThreads() {
    setLoading(true); setErr("");
    try {
      const x = await jget(`/api/v1/tenants/${tenantId}/whatsapp-threads?limit=200`);
      setThreads(x.items || []);
    } catch (e: any) {
      setErr(e.message || "Could not load threads");
    }
    setLoading(false);
  }

  async function openThread(phone: string) {
    setStatus("");
    try {
      const x = await jget(`/api/v1/tenants/${tenantId}/whatsapp-threads/${encodeURIComponent(phone)}`);
      setSelected(x);
      setReply("");
    } catch (e: any) {
      setStatus(e.message || "Could not load thread");
    }
  }

  async function send() {
    if (!selected || !reply.trim()) return;
    setSending(true); setStatus("");
    try {
      const r = await fetch(
        api() + `/api/v1/tenants/${tenantId}/whatsapp-threads/${encodeURIComponent(selected.phone)}/reply`,
        { method: "POST", headers: h, body: JSON.stringify({ body: reply.trim() }) }
      );
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Send failed");
      setReply("");
      await openThread(selected.phone);
      await loadThreads();
    } catch (e: any) {
      setStatus(e.message);
    }
    setSending(false);
  }

  useEffect(() => {
    if (!tenantId) return;
    void loadThreads();
    const iv = setInterval(() => { void loadThreads(); }, 30000);
    return () => clearInterval(iv);
  }, [tenantId]);

  function fmt(iso: string) {
    if (!iso) return "";
    const d = new Date(iso.endsWith("Z") ? iso : iso + "Z");
    return d.toLocaleString();
  }

  const filtered = threads.filter((t) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      (t.phone || "").toLowerCase().includes(q) ||
      (t.contact_name || "").toLowerCase().includes(q) ||
      (t.last_body || "").toLowerCase().includes(q)
    );
  });

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 14, minHeight: 560 }}>

      {/* Left: contact list */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 12, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: 12, borderBottom: "1px solid #eef1f5" }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats…"
            style={{
              width: "100%", padding: "9px 12px", border: "1px solid #d7dce5",
              borderRadius: 8, fontSize: 13, outline: "none", boxSizing: "border-box",
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, fontSize: 11, color: "#8490a4" }}>
            <span>{filtered.length} chat{filtered.length === 1 ? "" : "s"}</span>
            <button onClick={loadThreads} disabled={loading}
              style={{ background: "none", border: 0, color: "#5b5cf0", cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
              {loading ? "Loading…" : "Refresh"}
            </button>
          </div>
        </div>

        <div style={{ overflowY: "auto", flex: 1 }}>
          {err && <div style={{ padding: 12, color: "#b00", fontSize: 12 }}>{err}</div>}
          {filtered.length === 0 && !err && !loading && (
            <div style={{ padding: 20, color: "#98a2b4", fontSize: 12, textAlign: "center" }}>
              No chats yet. Incoming WhatsApp messages will appear here once your channel is connected.
            </div>
          )}
          {filtered.map((t) => (
            <button
              key={t.phone}
              onClick={() => openThread(t.phone)}
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "12px 14px", border: 0, borderBottom: "1px solid #f4f6fa",
                background: selected?.phone === t.phone ? "#eef4ff" : "transparent",
                cursor: "pointer",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "baseline" }}>
                <strong style={{ fontSize: 13, color: "#17213a", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {t.contact_name || t.phone}
                </strong>
                <span style={{ fontSize: 11, color: "#98a2b4", flexShrink: 0 }}>
                  {fmt(t.last_at).split(",")[0]}
                </span>
              </div>
              <div style={{ fontSize: 12, color: "#4b5563", marginTop: 3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {t.last_direction === "outbound" ? "You: " : ""}{t.last_body || "(no message)"}
              </div>
              {t.unread > 0 && (
                <div style={{ marginTop: 6, display: "inline-block", background: "#25D366", color: "#fff", borderRadius: 20, padding: "1px 8px", fontSize: 10, fontWeight: 700 }}>
                  {t.unread}
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Right: chat thread */}
      <div style={{ background: "#efeae2", border: "1px solid #e8ecf3", borderRadius: 12, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {!selected ? (
          <div style={{ margin: "auto", padding: 40, color: "#667781", fontSize: 13 }}>
            Select a chat to read.
          </div>
        ) : (
          <>
            <div style={{ padding: "14px 18px", background: "#f0f2f5", borderBottom: "1px solid #e0e3e7", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#111b21" }}>
                  {selected.contact_name || selected.phone}
                </div>
                <div style={{ fontSize: 12, color: "#667781", marginTop: 2 }}>
                  {selected.phone} · {selected.message_count} message{selected.message_count === 1 ? "" : "s"}
                </div>
              </div>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: 18, maxHeight: 400 }}>
              {selected.messages.map((m) => {
                const out = m.direction === "outbound";
                return (
                  <div key={m.id} style={{ display: "flex", justifyContent: out ? "flex-end" : "flex-start", marginBottom: 10 }}>
                    <div
                      style={{
                        maxWidth: "70%", padding: "8px 12px", borderRadius: 10,
                        background: out ? "#d9fdd3" : "#fff",
                        boxShadow: "0 1px 1px rgba(0,0,0,0.05)",
                      }}
                    >
                      <div style={{ fontSize: 13.5, color: "#111b21", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                        {m.body || "(empty)"}
                      </div>
                      <div style={{ fontSize: 10, color: "#667781", textAlign: "right", marginTop: 3 }}>
                        {fmt(m.created_at).split(", ").pop()}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ padding: 12, background: "#f0f2f5", borderTop: "1px solid #e0e3e7" }}>
              {status && (
                <div style={{ fontSize: 12, color: status.toLowerCase().includes("sent") ? "#1aa76c" : "#b00", marginBottom: 8 }}>
                  {status}
                </div>
              )}
              <div style={{ display: "flex", gap: 8 }}>
                <textarea
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                  placeholder="Type a message…"
                  rows={2}
                  style={{
                    flex: 1, padding: 10, border: 0, borderRadius: 8,
                    fontSize: 13.5, fontFamily: "inherit", outline: "none", resize: "none",
                    boxSizing: "border-box",
                  }}
                />
                <button
                  onClick={send}
                  disabled={sending || !reply.trim()}
                  style={{
                    background: "#25D366", color: "#fff", border: 0,
                    padding: "0 18px", borderRadius: 8, fontWeight: 700, fontSize: 13,
                    cursor: sending || !reply.trim() ? "not-allowed" : "pointer",
                    opacity: sending || !reply.trim() ? 0.6 : 1,
                  }}
                >
                  {sending ? "…" : "Send"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}