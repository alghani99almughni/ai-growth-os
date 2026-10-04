"use client";
import { useEffect, useState } from "react";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type Account = {
  id: string;
  label: string;
  provider: string;
  email_address: string;
  role: string;
  is_active: boolean;
  auto_reply_enabled: boolean;
  last_checked_at: string | null;
  last_error: string | null;
};

type Row = {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  industry: string;
  status: string;
  account_count: number;
  active_count: number;
  auto_reply_count: number;
  accounts: Account[];
  activity_24h: Record<string, number>;
};

type Totals = {
  tenants: number;
  tenants_with_email: number;
  total_accounts: number;
  total_active: number;
  total_errors: number;
};

export default function PlatformEmailPage() {
  const [data, setData] = useState<{ totals: Totals; items: Row[] } | null>(null);
  const [open, setOpen] = useState<string>("");
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) { window.location.href = "/login"; return; }
    fetch(API + "/api/v1/platform/email/overview", {
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
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Email across all tenants</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Every mailbox, poller state, and 24-hour activity — platform-wide.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 24 }}>
        <Kpi label="Tenants" value={data.totals.tenants} />
        <Kpi label="With email" value={data.totals.tenants_with_email} />
        <Kpi label="Mailboxes" value={data.totals.total_accounts} />
        <Kpi label="Active" value={data.totals.total_active} />
        <Kpi label="Errors" value={data.totals.total_errors} accent={data.totals.total_errors > 0 ? "#b00" : undefined} />
      </div>

      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead style={{ background: "#fafbfd" }}>
            <tr>
              <th style={th}>Tenant</th>
              <th style={th}>Industry</th>
              <th style={th}>Mailboxes</th>
              <th style={th}>Auto-reply</th>
              <th style={th}>24h activity</th>
              <th style={th}>Last error</th>
              <th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((r) => {
              const errors = r.accounts.filter((a) => a.last_error).length;
              const replied = r.activity_24h["replied"] || 0;
              const tickets = r.activity_24h["ticket_created"] || 0;
              const failed = r.activity_24h["failed"] || 0;
              const isOpen = open === r.tenant_id;
              return (
                <>
                  <tr key={r.tenant_id} style={{ borderTop: "1px solid #f1f4f8" }}>
                    <td style={td}>
                      <strong style={{ color: "#17213a" }}>{r.tenant_name}</strong>
                      <div style={{ color: "#8b95a5", fontSize: 11 }}>/{r.tenant_slug}</div>
                    </td>
                    <td style={td}>{r.industry}</td>
                    <td style={td}>{r.account_count}</td>
                    <td style={td}>{r.auto_reply_count}</td>
                    <td style={td}>
                      {replied > 0 && <span style={chip("#e9faf2", "#1d9c68")}>{replied} replied</span>}
                      {tickets > 0 && <span style={chip("#f1ebff", "#6b4fbb")}>{tickets} tickets</span>}
                      {failed > 0 && <span style={chip("#fff1f1", "#c74646")}>{failed} failed</span>}
                      {replied + tickets + failed === 0 && <span style={{ color: "#98a2b4" }}>—</span>}
                    </td>
                    <td style={td}>
                      {errors > 0 ? <span style={{ color: "#c74646" }}>{errors} mailbox{errors > 1 ? "es" : ""}</span> : <span style={{ color: "#98a2b4" }}>—</span>}
                    </td>
                    <td style={td}>
                      {r.account_count > 0 && (
                        <button
                          onClick={() => setOpen(isOpen ? "" : r.tenant_id)}
                          style={{ background: "transparent", border: 0, color: "#5b5cf0", fontWeight: 600, cursor: "pointer", fontSize: 12 }}
                        >
                          {isOpen ? "Hide" : "Details"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={7} style={{ background: "#fafbfd", padding: 0 }}>
                        <div style={{ padding: 16 }}>
                          {r.accounts.map((a) => (
                            <div key={a.id} style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 10, padding: 14, marginBottom: 8 }}>
                              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 6 }}>
                                <strong style={{ color: "#17213a" }}>{a.email_address}</strong>
                                <span style={chip("#eaf0ff", "#4d6df3")}>{a.provider}</span>
                                <span style={chip("#f1ebff", "#6b4fbb")}>{a.role}</span>
                                <span style={chip(a.is_active ? "#e9faf2" : "#f2f4f8", a.is_active ? "#1d9c68" : "#6b7686")}>{a.is_active ? "active" : "paused"}</span>
                                {a.auto_reply_enabled && <span style={chip("#e9faf2", "#1d9c68")}>auto-reply on</span>}
                              </div>
                              <div style={{ fontSize: 12, color: "#75839a" }}>
                                {a.label} · last checked {a.last_checked_at ? new Date(a.last_checked_at).toLocaleString() : "never"}
                              </div>
                              {a.last_error && <div style={{ fontSize: 12, color: "#c74646", marginTop: 4 }}>{a.last_error}</div>}
                            </div>
                          ))}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18 }}>
      <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: accent || "#17213a", marginTop: 4 }}>{value}</div>
    </div>
  );
}

const chip = (bg: string, fg: string): React.CSSProperties => ({
  display: "inline-block", padding: "2px 8px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: bg, color: fg, marginRight: 4,
});

const th: React.CSSProperties = {
  textAlign: "left", padding: "12px 16px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5",
};

const td: React.CSSProperties = {
  padding: "13px 16px", color: "#4b5563", verticalAlign: "top",
};