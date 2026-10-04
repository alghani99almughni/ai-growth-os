"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Tenant = {
  id: string;
  name: string;
  slug: string;
  industry: string;
  status: string;
  city: string | null;
  phone: string | null;
  created_at: string | null;
  last_seen_at: string | null;
  health_score: number;
  health_band: string;
};

export default function TenantsPage() {
  const [items, setItems] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) { window.location.href = "/login"; return; }
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (statusFilter) params.set("status", statusFilter);
    fetch(api() + "/api/v1/platform/tenants?" + params.toString(), {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
    })
      .then((r) => {
        if (r.status === 401 || r.status === 403) { window.location.href = "/login"; throw new Error("auth"); }
        return r.json();
      })
      .then((x) => { setItems(x.items || []); setLoading(false); })
      .catch((e) => { if (e.message !== "auth") setError(e.message || "Failed to load"); setLoading(false); });
  }, [search, statusFilter]);

  function bandColor(band: string) {
    if (band === "healthy") return { bg: "#e9faf2", fg: "#1d9c68" };
    if (band === "watch") return { bg: "#fff9e6", fg: "#c98c1a" };
    if (band === "at_risk") return { bg: "#fff0df", fg: "#e99132" };
    if (band === "critical") return { bg: "#fff1f1", fg: "#c74646" };
    return { bg: "#f2f4f8", fg: "#6b7686" };
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Tenants</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>{items.length} total · click a row to open</p>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <input
          placeholder="Search by name or slug…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1, minWidth: 220, padding: "11px 14px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, outline: "none" }}
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ padding: "11px 14px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, background: "#fff", minWidth: 150 }}>
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
          <option value="pending">Pending</option>
          <option value="closed">Closed</option>
        </select>
      </div>

      {error && <p style={{ color: "#b00", marginBottom: 12 }}>{error}</p>}

      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: "#75839a" }}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px dashed #dbe1ea", borderRadius: 14 }}>
          <h3 style={{ margin: "0 0 6px", color: "#17213a", fontSize: 15 }}>No tenants match</h3>
          <p style={{ margin: 0, fontSize: 13 }}>Try a different search or clear the filter.</p>
        </div>
      ) : (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#fafbfd" }}>
              <tr>
                <th style={thStyle}>Business</th>
                <th style={thStyle}>Industry</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Health</th>
                <th style={thStyle}>Last seen</th>
                <th style={thStyle}>Created</th>
                <th style={thStyle}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => {
                const c = bandColor(t.health_band);
                return (
                  <tr key={t.id} style={{ borderTop: "1px solid #f1f4f8" }}>
                    <td style={tdStyle}>
                      <strong style={{ color: "#17213a" }}>{t.name}</strong>
                      <div style={{ color: "#8b95a5", fontSize: 11 }}>/{t.slug}</div>
                    </td>
                    <td style={tdStyle}>{t.industry}</td>
                    <td style={tdStyle}>
                      <span style={{ display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: t.status === "active" ? "#e9faf2" : "#fff0df", color: t.status === "active" ? "#1d9c68" : "#e99132" }}>{t.status}</span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: c.bg, color: c.fg }}>
                        {t.health_score} · {t.health_band}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      {t.last_seen_at ? new Date(t.last_seen_at).toLocaleDateString() : "-"}
                    </td>
                    <td style={tdStyle}>
                      {t.created_at ? new Date(t.created_at).toLocaleDateString() : "-"}
                    </td>
                    <td style={tdStyle}>
                      <a href={"/platform/tenants/" + t.id} style={{ color: "#5b5cf0", fontWeight: 600, textDecoration: "none", fontSize: 12, marginRight: 12 }}>Details</a>
                                            <a href={"/customer?business=" + t.slug} target="_blank" rel="noreferrer" style={{ color: "#5b5cf0", fontWeight: 600, textDecoration: "none", fontSize: 12 }}>Open site ↗</a>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const thStyle: React.CSSProperties = { textAlign: "left", padding: "12px 16px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5" };

const tdStyle: React.CSSProperties = { padding: "13px 16px", color: "#4b5563", verticalAlign: "top" };
