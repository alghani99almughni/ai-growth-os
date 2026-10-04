"use client";
import { useEffect, useState } from "react";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type Row = {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  industry: string;
  status: string;
  openwa_connected: boolean;
  openwa_status: string | null;
  openwa_phone: string | null;
  meta_connected: boolean;
  meta_status: string | null;
  meta_phone: string | null;
  priority: string;
  active: string | null;
};

type Totals = {
  tenants: number;
  with_openwa: number;
  with_meta: number;
  with_any_channel: number;
};

export default function PlatformWhatsappPage() {
  const [data, setData] = useState<{ totals: Totals; items: Row[] } | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) { window.location.href = "/login"; return; }
    fetch(API + "/api/v1/platform/whatsapp/overview", {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
    })
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((x) => { setData(x); setLoading(false); })
      .catch((e) => { setErr("Load failed (" + e + ")"); setLoading(false); });
  }, []);

  if (loading) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  if (err) return <div style={{ padding: 40, color: "#b00" }}>{err}</div>;
  if (!data) return null;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>WhatsApp across all tenants</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          OpenWA and Meta Cloud API status for every tenant on the platform.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 24 }}>
        <Kpi label="Tenants" value={data.totals.tenants} />
        <Kpi label="With OpenWA" value={data.totals.with_openwa} />
        <Kpi label="With Meta" value={data.totals.with_meta} />
        <Kpi label="With any channel" value={data.totals.with_any_channel} />
      </div>

      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead style={{ background: "#fafbfd" }}>
            <tr>
              <th style={th}>Tenant</th>
              <th style={th}>Industry</th>
              <th style={th}>OpenWA</th>
              <th style={th}>Meta</th>
              <th style={th}>Priority</th>
              <th style={th}>Active now</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => (
              <tr key={r.tenant_id} style={{ borderTop: "1px solid #f1f4f8" }}>
                <td style={td}>
                  <strong style={{ color: "#17213a" }}>{r.tenant_name}</strong>
                  <div style={{ color: "#8b95a5", fontSize: 11 }}>/{r.tenant_slug}</div>
                </td>
                <td style={td}>{r.industry}</td>
                <td style={td}>
                  <span style={chip(r.openwa_connected ? "#e9faf2" : "#f2f4f8", r.openwa_connected ? "#1d9c68" : "#6b7686")}>
                    {r.openwa_connected ? "connected" : r.openwa_status || "not connected"}
                  </span>
                  {r.openwa_phone && <div style={{ fontSize: 11, color: "#8b95a5", marginTop: 3 }}>{r.openwa_phone}</div>}
                </td>
                <td style={td}>
                  <span style={chip(r.meta_connected ? "#e9faf2" : "#f2f4f8", r.meta_connected ? "#1d9c68" : "#6b7686")}>
                    {r.meta_connected ? "connected" : r.meta_status || "not connected"}
                  </span>
                  {r.meta_phone && <div style={{ fontSize: 11, color: "#8b95a5", marginTop: 3 }}>{r.meta_phone}</div>}
                </td>
                <td style={td}>{r.priority}</td>
                <td style={td}>{r.active ? <span style={chip("#eaf0ff", "#4d6df3")}>{r.active}</span> : <span style={{ color: "#98a2b4" }}>—</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18 }}>
      <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: "#17213a", marginTop: 4 }}>{value}</div>
    </div>
  );
}

const chip = (bg: string, fg: string): React.CSSProperties => ({
  display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: bg, color: fg,
});

const th: React.CSSProperties = {
  textAlign: "left", padding: "12px 16px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5",
};

const td: React.CSSProperties = {
  padding: "13px 16px", color: "#4b5563", verticalAlign: "top",
};