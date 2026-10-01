"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Service = {
  id: string;
  name: string;
  description: string | null;
  price: number | null;
  currency: string | null;
  duration_minutes: number | null;
  is_active: boolean;
};

function fmtPrice(price: number | null, currency: string | null): string {
  if (price === null || price === undefined) return "—";
  const cur = currency || "INR";
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: cur,
      maximumFractionDigits: 2,
    }).format(price);
  } catch {
    return `${cur} ${price}`;
  }
}

export default function ServicesPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [items, setItems] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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
      const res = await jget(`/api/v1/tenants/${tenantId}/services`);
      setItems(res.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load services");
    }
    setLoading(false);
  }

  useEffect(() => {
    if (tenantId) void loadAll();
  }, [tenantId]);

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
          <h2 style={{ margin: 0 }}>🛍️ Services</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            {items.length} total service{items.length === 1 ? "" : "s"}.
          </p>
        </div>
        <button className="btn-ghost" onClick={loadAll} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>}

      <div style={{ marginTop: 20 }}>
        {items.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No services yet</h3>
            <p>Add services to your business so customers can book them.</p>
          </div>
        )}

        {items.map((s) => (
          <article
            key={s.id}
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
                  <strong style={{ fontSize: 14 }}>{s.name}</strong>
                  <span className="badge badge-blue">{fmtPrice(s.price, s.currency)}</span>
                  {s.duration_minutes ? (
                    <span className="badge badge-purple">{s.duration_minutes} min</span>
                  ) : null}
                  {!s.is_active && <span className="badge badge-grey">inactive</span>}
                </div>
                {s.description && (
                  <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                    {s.description}
                  </p>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>

      <p style={{ marginTop: 20, fontSize: 12, color: "#98a2b4" }}>
        Create, edit, and archive services — coming in v2.
      </p>
    </section>
  );
}