"use client";
import { useEffect, useState } from "react";

const api = () =>
  String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type ThreadSummary = {
  thread_id: string;
  subject: string;
  from_address: string;
  to_address: string;
  last_at: string;
  message_count: number;
  unread: number;
  has_ticket: boolean;
};

type ThreadMessage = {
  id: string;
  message_id: string;
  from_address: string;
  to_address: string;
  subject: string;
  body: string;
  reply_text: string | null;
  outcome: string;
  in_reply_to: string | null;
  references_header: string | null;
  created_at: string;
};

type ThreadDetail = ThreadSummary & { messages: ThreadMessage[] };

export default function EmailInboxPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [threads, setThreads] = useState<ThreadSummary[]>([]);
  const [selected, setSelected] = useState<ThreadDetail | null>(null);
  const [query, setQuery] = useState("");
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

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
    setLoading(true); setError("");
    try {
      const x = await jget(`/api/v1/tenants/${tenantId}/email-threads?limit=200`);
      setThreads(x.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load threads");
    }
    setLoading(false);
  }

  async function openThread(id: string) {
    setStatus("");
    try {
      const x = await jget(`/api/v1/tenants/${tenantId}/email-threads/${id}`);
      setSelected(x);
      setReplyText("");
    } catch (e: any) {
      setStatus(e.message || "Could not load thread");
    }
  }

  async function sendReply() {
    if (!selected || !replyText.trim()) return;
    setSending(true); setStatus("");
    try {
      const r = await fetch(
        api() + `/api/v1/tenants/${tenantId}/email-threads/${selected.thread_id}/reply`,
        { method: "POST", headers: h, body: JSON.stringify({ body: replyText.trim() }) }
      );
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Reply failed");
      setStatus("Reply sent");
      setReplyText("");
      await openThread(selected.thread_id);
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
      t.subject?.toLowerCase().includes(q) ||
      t.from_address?.toLowerCase().includes(q) ||
      t.to_address?.toLowerCase().includes(q)
    );
  });

  return (
    <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 14, minHeight: 560 }}>

      {/* Left: thread list */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 12, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ padding: 12, borderBottom: "1px solid #eef1f5" }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search mail…"
            style={{
              width: "100%", padding: "9px 12px", border: "1px solid #d7dce5",
              borderRadius: 8, fontSize: 13, outline: "none", boxSizing: "border-box"
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, fontSize: 11, color: "#8490a4" }}>
            <span>{filtered.length} thread{filtered.length === 1 ? "" : "s"}</span>
            <button
              onClick={loadThreads}
              disabled={loading}
              style={{ background: "none", border: 0, color: "#5b5cf0", cursor: "pointer", fontSize: 11, fontWeight: 600 }}
            >
              {loading ? "Loading…" : "Refresh"}
            </button>
          </div>
        </div>

        <div style={{ overflowY: "auto", flex: 1 }}>
          {error && <div style={{ padding: 12, color: "#b00", fontSize: 12 }}>{error}</div>}
          {filtered.length === 0 && !error && !loading && (
            <div style={{ padding: 20, color: "#98a2b4", fontSize: 12, textAlign: "center" }}>
              No threads yet.
            </div>
          )}
          {filtered.map((t) => (
            <button
              key={t.thread_id}
              onClick={() => openThread(t.thread_id)}
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "12px 14px", border: 0, borderBottom: "1px solid #f4f6fa",
                background: selected?.thread_id === t.thread_id ? "#eef4ff" : "transparent",
                cursor: "pointer",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "baseline" }}>
                <strong
                  style={{
                    fontSize: 13, color: "#17213a",
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    fontWeight: t.unread > 0 ? 800 : 600,
                  }}
                >
                  {t.from_address}
                </strong>
                <span style={{ fontSize: 11, color: "#98a2b4", flexShrink: 0 }}>
                  {fmt(t.last_at).split(",")[0]}
                </span>
              </div>
              <div
                style={{
                  fontSize: 12, color: "#4b5563", marginTop: 3,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}
              >
                {t.subject || "(no subject)"}
              </div>
              <div style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center" }}>
                {t.message_count > 1 && (
                  <span style={{ fontSize: 10.5, color: "#75839a" }}>{t.message_count} msgs</span>
                )}
                {t.has_ticket && (
                  <span style={{ fontSize: 10, padding: "2px 7px", borderRadius: 20, background: "#f1ebff", color: "#6b4fbb", fontWeight: 700 }}>
                    ticket
                  </span>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right: thread view */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 12, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {!selected ? (
          <div style={{ margin: "auto", padding: 40, color: "#98a2b4", fontSize: 13 }}>
            Select a thread to read.
          </div>
        ) : (
          <>
            <div style={{ padding: "14px 18px", borderBottom: "1px solid #eef1f5" }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: "#17213a" }}>
                {selected.subject || "(no subject)"}
              </div>
              <div style={{ fontSize: 12, color: "#75839a", marginTop: 4 }}>
                {selected.message_count} message{selected.message_count === 1 ? "" : "s"} · from {selected.from_address}
              </div>
            </div>

            <div style={{ flex: 1, overflowY: "auto", padding: 18, maxHeight: 380 }}>
              {selected.messages.map((m) => (
                <div
                  key={m.id}
                  style={{
                    marginBottom: 14, padding: 14, borderRadius: 10,
                    background: m.reply_text ? "#f6f8ff" : "#fafbfc",
                    border: "1px solid #eef1f5",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 8 }}>
                    <strong style={{ fontSize: 12.5, color: "#17213a" }}>{m.from_address}</strong>
                    <span style={{ fontSize: 11, color: "#98a2b4" }}>{fmt(m.created_at)}</span>
                  </div>
                  {m.body && (
                    <pre style={{ margin: 0, fontFamily: "inherit", fontSize: 13, color: "#4b5563", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                      {m.body}
                    </pre>
                  )}
                  {m.reply_text && (
                    <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px dashed #d7dce5" }}>
                      <div style={{ fontSize: 11, color: "#75839a", marginBottom: 5, fontWeight: 600 }}>
                        ↳ Our reply
                      </div>
                      <pre style={{ margin: 0, fontFamily: "inherit", fontSize: 13, color: "#17213a", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                        {m.reply_text}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div style={{ padding: 14, borderTop: "1px solid #eef1f5" }}>
              {status && (
                <div style={{ fontSize: 12, color: status === "Reply sent" ? "#1aa76c" : "#b00", marginBottom: 8 }}>
                  {status}
                </div>
              )}
              <textarea
                value={replyText}
                onChange={(e) => setReplyText(e.target.value)}
                placeholder="Type your reply…"
                rows={4}
                style={{
                  width: "100%", padding: 12, border: "1px solid #d7dce5", borderRadius: 10,
                  fontSize: 13, fontFamily: "inherit", outline: "none",
                  boxSizing: "border-box", resize: "vertical",
                }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 10 }}>
                <button
                  onClick={sendReply}
                  disabled={sending || !replyText.trim()}
                  style={{
                    background: "linear-gradient(135deg, #5b5cf0, #7159f7)",
                    color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10,
                    fontWeight: 700, fontSize: 13,
                    cursor: sending ? "wait" : "pointer",
                    opacity: sending || !replyText.trim() ? 0.6 : 1,
                  }}
                >
                  {sending ? "Sending…" : "Send reply"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}