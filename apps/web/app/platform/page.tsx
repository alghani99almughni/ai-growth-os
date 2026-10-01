"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Overview = {
  total_tenants: number;
  active_tenants: number;
  total_customers: number;
  total_leads: number;
  total_orders: number;
  total_calls: number;
  signups_per_day: { date: string; count: number }[];
  recent_signups: { id: string; name: string; slug: string; industry: string; status: string; created_at: string | null }[];
};

export default function PlatformOverview() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) { window.location.href = "/login"; return; }
    fetch(api() + "/api/v1/platform/overview?days=30", {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
    })
      .then((r) => {
        if (r.status === 401 || r.status === 403) { window.location.href = "/login"; throw new Error("auth"); }
        return r.json();
      })
      .then((x) => { setData(x); setLoading(false); })
      .catch((e) => { if (e.message !== "auth") setError(e.message || "Failed to load"); setLoading(false); });
  }, []);

  if (loading) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  if (error) return <div style={{ padding: 40 }}><h1 style={{ margin: 0, color: "#17213a", fontSize: 24 }}>Platform Overview</h1><p style={{ color: "#b00", marginTop: 16 }}>{error}</p><p style={{ color: "#75839a", fontSize: 13 }}>Check that the API is running at {api()} and that your login is valid.</p></div>;
  if (!data) return <div style={{ padding: 40, color: "#75839a" }}>No data available.</div>;

  const maxSignups = Math.max(1, ...data.signups_per_day.map((x) => x.count));
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Platform Overview</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>Last 30 days across the entire platform.</p>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14, marginBottom: 24 }}>
        <Kpi label="Total tenants" value={data.total_tenants} accent="#5b5cf0" />
        <Kpi label="Active tenants" value={data.active_tenants} accent="#20aa72" />
        <Kpi label="Customers" value={data.total_customers} accent="#20a7a0" />
        <Kpi label="Leads" value={data.total_leads} accent="#8a62ed" />
        <Kpi label="Orders" value={data.total_orders} accent="#e99132" />
        <Kpi label="AI calls" value={data.total_calls} accent="#4d6df3" />
      </div>
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 15, color: "#17213a" }}>Signups - last 30 days</h2>
          <span style={{ color: "#75839a", fontSize: 12 }}>{data.signups_per_day.reduce((a, d) => a + d.count, 0)} new</span>
        </div>
        {data.signups_per_day.length === 0 ? (
          <p style={{ color: "#98a2b4", fontSize: 13, margin: 0 }}>No signups in the last 30 days.</p>
        ) : (
          <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 100, padding: "8px 0", background: "#fafbfd", borderRadius: 8 }}>
            {data.signups_per_day.map((d) => (
              <div key={d.date} title={d.date + ": " + d.count + " signups"} style={{ flex: 1, height: Math.max(6, (d.count / maxSignups) * 100) + "%", background: "linear-gradient(180deg, #5b5cf0, #7159f7)", borderRadius: 3, minWidth: 4 }} />
            ))}
          </div>
        )}
      </div>
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22 }}>
        <h2 style={{ margin: "0 0 14px", fontSize: 15, color: "#17213a" }}>Recent signups</h2>
        {data.recent_signups.length === 0 ? (
          <p style={{ color: "#98a2b4", fontSize: 13, margin: 0 }}>No tenants yet.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead><tr><th style={thStyle}>Name</th><th style={thStyle}>Industry</th><th style={thStyle}>Status</th><th style={thStyle}>Created</th><th style={thStyle}>Actions</th></tr></thead>
            <tbody>
              {data.recent_signups.map((t) => (
                <tr key={t.id} style={{ borderTop: "1px solid #f1f4f8" }}>
                  <td style={tdStyle}><strong style={{ color: "#17213a" }}>{t.name}</strong><div style={{ color: "#8b95a5", fontSize: 11 }}>/{t.slug}</div></td>
                  <td style={tdStyle}>{t.industry}</td>
                  <td style={tdStyle}><span style={{ display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: t.status === "active" ? "#e9faf2" : "#fff0df", color: t.status === "active" ? "#1d9c68" : "#e99132" }}>{t.status}</span></td>
                  <td style={tdStyle}>{t.created_at ? new Date(t.created_at).toLocaleDateString() : "-"}</td>
                  <td style={tdStyle}><a href={"/platform/tenants/" + t.id} style={{ color: "#5b5cf0", fontWeight: 600, textDecoration: "none", fontSize: 12 }}>Open →</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20 }}>
      <div style={{ width: 8, height: 8, borderRadius: 4, background: accent, marginBottom: 12 }} />
      <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color: "#17213a", marginTop: 4 }}>{value}</div>
    </div>
  );
}

const thStyle: React.CSSProperties = { textAlign: "left", padding: "10px 12px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5" };

const tdStyle: React.CSSProperties = { padding: "12px", color: "#4b5563", verticalAlign: "top" };
