"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type CallRecord = {
  id: string;
  customer_id: string | null;
  customer_name: string;
  source: string;
  status: string;
  department: string | null;
  staff_id: string | null;
  room_id: string | null;
  intent: string | null;
  summary: string | null;
  transcript: string | null;
  created_at: string;
};

const STATUS_COLOURS: Record<string, string> = {
  ringing: "badge-orange",
  ongoing: "badge-blue",
  in_progress: "badge-blue",
  completed: "badge-grey",
  resolved: "badge-grey",
  failed: "badge-grey",
  missed: "badge-grey",
};

function fmtWhen(iso: string): string {
  if (!iso) return "";
  try {
    const u = iso.endsWith("Z") ? iso : iso + "Z";
    return new Date(u).toLocaleString("en-IN", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}

export default function CallsPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [items, setItems] = useState<CallRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<string>("");
  const [openId, setOpenId] = useState<string>("");

  const authHeaders = () => ({ Authorization: "Bearer " + token });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const res = await jget(`/api/v1/tenants/${tenantId}/calls`);
      setItems(res.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load calls");
    }
    setLoading(false);
  }

  useEffect(() => {
    if (tenantId) void loadAll();
  }, [tenantId]);

  const visible = filter
    ? items.filter((c) => {
        const f = filter.toLowerCase();
        return (
          c.status?.toLowerCase().includes(f) ||
          c.intent?.toLowerCase().includes(f) ||
          c.customer_name?.toLowerCase().includes(f) ||
          c.summary?.toLowerCase().includes(f)
        );
      })
    : items;

  return (
    <section className="card">
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2 style={{ margin: 0 }}>📞 Calls</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            {items.length} total call{items.length === 1 ? "" : "s"}.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            placeholder="Filter by status, intent, customer…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{
              padding: "8px 10px",
              border: "1px solid #d7dde8",
              borderRadius: 8,
              fontSize: 13,
              minWidth: 240,
            }}
          />
          <button className="btn-ghost" onClick={loadAll} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>}

      <div style={{ marginTop: 20 }}>
        {visible.length === 0 && !loading && (
          <div className="empty-state">
            <h3>{filter ? "No matching calls" : "No calls yet"}</h3>
            <p>
              {filter
                ? "Try clearing the filter."
                : "Once your voice agent handles calls, they'll appear here."}
            </p>
          </div>
        )}

        {visible.map((c) => {
          const isOpen = openId === c.id;
          return (
            <article
              key={c.id}
              className="card"
              style={{ marginBottom: 12, padding: 16, background: "#fff" }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: 12,
                  flexWrap: "wrap",
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                    <strong style={{ fontSize: 15 }}>{c.customer_name}</strong>
                    <span className={"badge " + (STATUS_COLOURS[c.status] || "badge-grey")}>
                      {c.status}
                    </span>
                    {c.intent && <span className="badge badge-purple">{c.intent}</span>}
                    {c.source && <span className="badge badge-grey">{c.source}</span>}
                  </div>
                  {c.summary && (
                    <p style={{ margin: "6px 0 0", color: "#4a5875", fontSize: 13 }}>
                      {c.summary}
                    </p>
                  )}
                  <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                    {fmtWhen(c.created_at)}
                    {c.department ? <> · {c.department}</> : null}
                  </p>
                </div>

                {c.transcript && (
                  <button
                    className="btn-ghost"
                    onClick={() => setOpenId(isOpen ? "" : c.id)}
                  >
                    {isOpen ? "Hide" : "View"} transcript
                  </button>
                )}
              </div>

              {isOpen && c.transcript && (
                <pre
                  style={{
                    marginTop: 12,
                    padding: 12,
                    background: "#f6f8fc",
                    border: "1px solid #e8ecf3",
                    borderRadius: 10,
                    fontSize: 12,
                    lineHeight: 1.5,
                    color: "#33415c",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    maxHeight: 360,
                    overflowY: "auto",
                  }}
                >
                  {c.transcript}
                </pre>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}