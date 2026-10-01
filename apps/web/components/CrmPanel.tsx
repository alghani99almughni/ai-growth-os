"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Customer = {
  id: string;
  name: string | null;
  phone: string;
  email: string | null;
  address: string | null;
  notes: string | null;
  tags: string | null;
  source: string | null;
  whatsapp_opt_in: boolean | null;
  portal_token: string | null;
};

function parseTags(raw: string | null): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

export default function CrmPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [items, setItems] = useState<Customer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");

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
      const res = await jget(`/api/v1/tenants/${tenantId}/customers`);
      setItems(res.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load customers");
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
          (c.name || "").toLowerCase().includes(f) ||
          (c.phone || "").toLowerCase().includes(f) ||
          (c.email || "").toLowerCase().includes(f) ||
          (c.tags || "").toLowerCase().includes(f)
        );
      })
    : items;

  return (
    <section className="card">
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
          <h2 style={{ margin: 0 }}>👥 Customers</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            {items.length} total customer{items.length === 1 ? "" : "s"}.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            placeholder="Search name, phone, email, tags…"
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
            <h3>{filter ? "No matching customers" : "No customers yet"}</h3>
            <p>
              {filter
                ? "Try clearing the filter."
                : "Customers will appear here as soon as someone chats with your business."}
            </p>
          </div>
        )}

        {visible.map((c) => {
          const tags = parseTags(c.tags);
          return (
            <article
              key={c.id}
              className="card"
              style={{ marginBottom: 10, padding: 14, background: "#fff" }}
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
                    <strong style={{ fontSize: 14 }}>{c.name || "Unnamed"}</strong>
                    {c.whatsapp_opt_in && <span className="badge badge-blue">WhatsApp opted in</span>}
                    {c.source && <span className="badge badge-grey">{c.source}</span>}
                    {tags.map((t) => (
                      <span key={t} className="badge badge-purple">
                        {t}
                      </span>
                    ))}
                  </div>
                  <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                    📞 {c.phone}
                    {c.email ? <> · ✉️ {c.email}</> : null}
                  </p>
                  {c.address && (
                    <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 12 }}>
                      📍 {c.address}
                    </p>
                  )}
                  {c.notes && (
                    <p style={{ margin: "6px 0 0", color: "#4a5875", fontSize: 12 }}>
                      {c.notes}
                    </p>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <p style={{ marginTop: 20, fontSize: 12, color: "#98a2b4" }}>
        Edit contact details, share PWA link, and view interaction timeline — coming in v2.
      </p>
    </section>
  );
}