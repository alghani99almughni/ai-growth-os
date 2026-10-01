"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const STATUSES = ["new", "acknowledged", "in_progress", "waiting_on_tenant", "resolved", "closed"];

export default function TicketDetail() {
  const params = useParams();
  const id = (params?.id as string) || "";
  const [ticket, setTicket] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [replyText, setReplyText] = useState("");
  const [asTenant, setAsTenant] = useState(false);
  const [busy, setBusy] = useState(false);

  function headers() {
    return {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || ""),
    };
  }

  async function load() {
    setLoading(true);
    try {
      const r = await fetch(api() + "/api/v1/platform/tickets/" + id, {
        headers: { Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || "") },
        cache: "no-store",
      });
      if (r.status === 401 || r.status === 403) { window.location.href = "/login"; return; }
      if (!r.ok) throw new Error("Ticket not found");
      setTicket(await r.json());
    } catch (e: any) {
      setError(e.message || "Failed to load");
    }
    setLoading(false);
  }

  useEffect(() => { if (id) void load(); }, [id]);

  async function updateStatus(newStatus: string) {
    setBusy(true); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/tickets/" + id + "/status", {
        method: "PATCH", headers: headers(), body: JSON.stringify({ status: newStatus }),
      });
      if (!r.ok) throw new Error("Failed to update");
      setTicket(await r.json());
      setStatus("Status: " + newStatus);
    } catch (e: any) { setStatus(e.message); }
    setBusy(false);
  }

  async function submitReply() {
    if (!replyText.trim()) return;
    setBusy(true); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/tickets/" + id + "/reply", {
        method: "POST", headers: headers(),
        body: JSON.stringify({ message: replyText.trim(), from_tenant: asTenant }),
      });
      if (!r.ok) throw new Error("Failed to reply");
      setTicket(await r.json());
      setReplyText("");
      setStatus("Reply added");
    } catch (e: any) { setStatus(e.message); }
    setBusy(false);
  }

  if (loading) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading ticket…</div>;
  if (error) return <div style={{ padding: 40, color: "#b00" }}>{error}</div>;
  if (!ticket) return null;

  const slaTone = (() => {
    if (ticket.status === "resolved" || ticket.status === "closed") return { bg: "#f2f4f8", fg: "#6b7686", label: "Completed" };
    if (ticket.sla_breached) return { bg: "#fff1f1", fg: "#c74646", label: "Breached" };
    const rem = ticket.sla_remaining_seconds || 0;
    if (rem < 3600) return { bg: "#fff0df", fg: "#e99132", label: "Due " + Math.floor(rem / 60) + "m" };
    if (rem < 4 * 3600) return { bg: "#fff9e6", fg: "#c98c1a", label: "Due " + Math.floor(rem / 3600) + "h" };
    return { bg: "#e9faf2", fg: "#1d9c68", label: "On track" };
  })();

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <a href="/platform/tickets" style={{ color: "#5b5cf0", fontSize: 12, textDecoration: "none", fontWeight: 600 }}>← Back to tickets</a>
        <h1 style={{ margin: "10px 0 0", fontSize: 24, letterSpacing: "-0.03em", color: "#17213a" }}>{ticket.subject}</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          {ticket.category} · {ticket.priority} · tenant {ticket.tenant_id.slice(0, 12)}… · created {ticket.created_at ? new Date(ticket.created_at).toLocaleString() : "—"}
        </p>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 20, flexWrap: "wrap", alignItems: "center" }}>
        <span style={{ display: "inline-block", padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700, background: slaTone.bg, color: slaTone.fg }}>
          SLA: {slaTone.label}
        </span>
        <span style={{ display: "inline-block", padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700, background: "#edf2ff", color: "#566ce1" }}>
          Status: {ticket.status.replace(/_/g, " ")}
        </span>
        <span style={{ color: "#75839a", fontSize: 12 }}>
          SLA window: {ticket.sla_hours}h · due {ticket.sla_due_at ? new Date(ticket.sla_due_at).toLocaleString() : "—"}
        </span>
      </div>

      {/* Status buttons */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20, marginBottom: 18 }}>
        <h2 style={{ margin: "0 0 14px", fontSize: 14, color: "#17213a" }}>Change status</h2>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {STATUSES.map((s) => (
            <button
              key={s}
              onClick={() => updateStatus(s)}
              disabled={busy || s === ticket.status}
              style={{
                padding: "9px 16px",
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 600,
                border: "1px solid " + (s === ticket.status ? "transparent" : "#e5e7eb"),
                background: s === ticket.status ? "linear-gradient(135deg,#5b5cf0,#7159f7)" : "#fff",
                color: s === ticket.status ? "#fff" : "#17213a",
                cursor: busy || s === ticket.status ? "default" : "pointer",
              }}
            >
              {s.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      {/* Thread */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24, marginBottom: 18 }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 14, color: "#17213a" }}>Conversation</h2>
        <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.7, color: "#4b5563", fontFamily: "inherit" }}>
          {ticket.body || "(No messages yet)"}
        </div>
      </div>

      {/* Reply form */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20 }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 14, color: "#17213a" }}>Add a reply</h2>
        <textarea
          value={replyText}
          onChange={(e) => setReplyText(e.target.value)}
          placeholder="Type your reply…"
          rows={4}
          style={{ display: "block", width: "100%", padding: 12, borderRadius: 10, border: "1px solid #d7dce5", fontSize: 13, outline: "none", fontFamily: "inherit", resize: "vertical" }}
        />
        <div style={{ display: "flex", gap: 12, alignItems: "center", marginTop: 12, flexWrap: "wrap" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#4b5563" }}>
            <input type="checkbox" checked={asTenant} onChange={(e) => setAsTenant(e.target.checked)} style={{ width: "auto", margin: 0 }} />
            Post as tenant (simulate tenant reply)
          </label>
          <button
            onClick={submitReply}
            disabled={busy || !replyText.trim()}
            style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: busy ? "wait" : "pointer", marginLeft: "auto" }}
          >
            {busy ? "Sending…" : "Send reply"}
          </button>
        </div>
        {status && <p style={{ margin: "12px 0 0", fontSize: 12, color: "#1aa76c" }}>{status}</p>}
      </div>
    </div>
  );
}
