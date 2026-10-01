"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type OrderItem = {
  name: string;
  price: number;
  quantity: number;
  notes: string | null;
};

type Order = {
  id: string;
  status: string;
  context_token: string | null;
  subtotal: number;
  tax: number;
  discount: number;
  total: number;
  payment_status: string;
  items: OrderItem[];
  bill: { id: string; status: string; total: number } | null;
};

const STATUS_COLOURS: Record<string, string> = {
  pending: "badge-orange",
  confirmed: "badge-blue",
  preparing: "badge-purple",
  ready: "badge-purple",
  delivered: "badge-blue",
  completed: "badge-grey",
  cancelled: "badge-grey",
};

const PAYMENT_COLOURS: Record<string, string> = {
  paid: "badge-blue",
  unpaid: "badge-orange",
  refunded: "badge-grey",
};

function fmtMoney(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return `₹${n}`;
  }
}

export default function OrdersPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [items, setItems] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");

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
      const qs = statusFilter ? `?status=${encodeURIComponent(statusFilter)}` : "";
      const res = await jget(`/api/v1/tenants/${tenantId}/orders${qs}`);
      setItems(res.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load orders");
    }
    setLoading(false);
  }

  useEffect(() => {
    if (tenantId) void loadAll();
  }, [tenantId, statusFilter]);

  const totalRevenue = items
    .filter((o) => o.payment_status === "paid")
    .reduce((acc, o) => acc + (o.total || 0), 0);

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
          <h2 style={{ margin: 0 }}>🧾 Orders</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            {items.length} order{items.length === 1 ? "" : "s"} shown
            {totalRevenue > 0 ? <> · {fmtMoney(totalRevenue)} paid</> : null}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              padding: "8px 10px",
              border: "1px solid #d7dde8",
              borderRadius: 8,
              fontSize: 13,
            }}
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="confirmed">Confirmed</option>
            <option value="preparing">Preparing</option>
            <option value="ready">Ready</option>
            <option value="delivered">Delivered</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button className="btn-ghost" onClick={loadAll} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>}

      <div style={{ marginTop: 20 }}>
        {items.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No orders yet</h3>
            <p>Orders placed via your PWA or QR codes will appear here.</p>
          </div>
        )}

        {items.map((o) => (
          <article
            key={o.id}
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
                {/* Header badges */}
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <strong style={{ fontSize: 14 }}>
                    {fmtMoney(o.total)}{" "}
                    <span style={{ color: "#75839a", fontWeight: 400, fontSize: 12 }}>
                      ({o.items.length} item{o.items.length === 1 ? "" : "s"})
                    </span>
                  </strong>
                  <span className={"badge " + (STATUS_COLOURS[o.status] || "badge-grey")}>
                    {o.status}
                  </span>
                  <span className={"badge " + (PAYMENT_COLOURS[o.payment_status] || "badge-grey")}>
                    {o.payment_status}
                  </span>
                  {o.bill && <span className="badge badge-grey">bill: {o.bill.status}</span>}
                </div>

                {/* Line items */}
                <ul
                  style={{
                    margin: "10px 0 0",
                    padding: "0 0 0 18px",
                    color: "#33415c",
                    fontSize: 13,
                    lineHeight: 1.7,
                  }}
                >
                  {o.items.map((it, i) => (
                    <li key={i}>
                      {it.quantity}× {it.name} — {fmtMoney(it.price)}
                      {it.notes ? (
                        <span style={{ color: "#75839a" }}> · {it.notes}</span>
                      ) : null}
                    </li>
                  ))}
                </ul>

                {/* Totals */}
                <p style={{ margin: "8px 0 0", color: "#75839a", fontSize: 12 }}>
                  Subtotal {fmtMoney(o.subtotal)}
                  {o.tax ? <> · Tax {fmtMoney(o.tax)}</> : null}
                  {o.discount ? <> · Discount −{fmtMoney(o.discount)}</> : null}
                </p>

                {o.context_token && (
                  <p
                    style={{
                      margin: "6px 0 0",
                      fontFamily: "monospace",
                      fontSize: 11,
                      color: "#98a2b4",
                    }}
                  >
                    context: {o.context_token}
                  </p>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>

      <p style={{ marginTop: 20, fontSize: 12, color: "#98a2b4" }}>
        Change order status, print bill, refund — coming in v2.
      </p>
    </section>
  );
}