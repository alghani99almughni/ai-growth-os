"""Write the platform tickets list page."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "platform" / "tickets" / "page.tsx"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = '''"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Ticket = {
  id: string;
  tenant_id: string;
  subject: string;
  category: string;
  priority: string;
  status: string;
  sla_hours: number;
  sla_due_at: string | null;
  sla_remaining_seconds: number | null;
  sla_breached: boolean;
  assigned_to: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export default function TicketsPage() {
  const [items, setItems] = useState<Ticket[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [breachedOnly, setBreachedOnly] = useState(false);

  function headers() {
    return { Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || "") };
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (categoryFilter) params.set("category", categoryFilter);
      if (breachedOnly) params.set("include_breached_only", "true");
      const r = await fetch(api() + "/api/v1/platform/tickets?" + params.toString(), {
        headers: headers(),
        cache: "no-store",
      });
      if (r.status === 401 || r.status === 403) { window.location.href = "/login"; return; }
      const x = await r.json();
      setItems(x.items || []);
      setSummary(x.summary || null);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    }
    setLoading(false);
  }

  useEffect(() => { void load(); }, [statusFilter, categoryFilter, breachedOnly]);

  function slaTone(t: Ticket) {
    if (t.status === "resolved" || t.status === "closed") return { bg: "#f2f4f8", fg: "#6b7686", label: "Done" };
    if (t.sla_breached) return { bg: "#fff1f1", fg: "#c74646", label: "Breached" };
    const rem = t.sla_remaining_seconds || 0;
    if (rem < 3600) return { bg: "#fff0df", fg: "#e99132", label: formatDuration(rem) };
    if (rem < 4 * 3600) return { bg: "#fff9e6", fg: "#c98c1a", label: formatDuration(rem) };
    return { bg: "#e9faf2", fg: "#1d9c68", label: formatDuration(rem) };
  }

  function formatDuration(sec: number) {
    if (sec < 0) return "overdue";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (h > 0) return h + "h " + m + "m";
    return m + "m";
  }

  const statusTone = (s: string) => {
    if (s === "new") return { bg: "#edf2ff", fg: "#566ce1" };
    if (s === "acknowledged") return { bg: "#e5f8f8", fg: "#20a7a0" };
    if (s === "in_progress") return { bg: "#f0eaff", fg: "#7a55d6" };
    if (s === "waiting_on_tenant") return { bg: "#fff9e6", fg: "#c98c1a" };
    if (s === "resolved") return { bg: "#e9faf2", fg: "#1d9c68" };
    if (s === "closed") return { bg: "#f2f4f8", fg: "#6b7686" };
    return { bg: "#f2f4f8", fg: "#6b7686" };
  };

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Support Tickets</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Tenant concerns, SLA tracking, resolution. Click a row to open.
        </p>
      </div>

      {summary && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 18 }}>
          <SummaryCard label="Open" value={summary.open} accent="#5b5cf0" />
          <SummaryCard label="Breached SLA" value={summary.breached} accent="#c74646" />
          <SummaryCard label="Due within 1h" value={summary.due_within_hour} accent="#e99132" />
          <SummaryCard label="Healthy" value={summary.healthy} accent="#1d9c68" />
        </div>
      )}

      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={selectStyle}>
          <option value="">All statuses</option>
          <option value="open">Open (any)</option>
          <option value="new">New</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="in_progress">In progress</option>
          <option value="waiting_on_tenant">Waiting on tenant</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} style={selectStyle}>
          <option value="">All categories</option>
          <option value="support">Support</option>
          <option value="billing">Billing</option>
          <option value="contact">Contact</option>
          <option value="critical">Critical</option>
        </select>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#17213a", cursor: "pointer", padding: "10px 14px", background: "#fff", border: "1px solid #d7dce5", borderRadius: 10 }}>
          <input type="checkbox" checked={breachedOnly} onChange={(e) => setBreachedOnly(e.target.checked)} style={{ width: "auto", margin: 0 }} />
          SLA breached only
        </label>
      </div>

      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px dashed #dbe1ea", borderRadius: 14 }}>
          <h3 style={{ margin: "0 0 6px", color: "#17213a", fontSize: 15 }}>No tickets</h3>
          <p style={{ margin: 0, fontSize: 13 }}>Tickets submitted by tenants will appear here.</p>
        </div>
      ) : (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#fafbfd" }}>
              <tr>
                <th style={thStyle}>Subject</th>
                <th style={thStyle}>Category</th>
                <th style={thStyle}>Priority</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>SLA</th>
                <th style={thStyle}>Created</th>
                <th style={thStyle}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {items.map((t) => {
                const st = statusTone(t.status);
                const sla = slaTone(t);
                return (
                  <tr key={t.id} style={{ borderTop: "1px solid #f1f4f8" }}>
                    <td style={tdStyle}>
                      <strong style={{ color: "#17213a" }}>{t.subject}</strong>
                      <div style={{ color: "#8b95a5", fontSize: 11 }}>tenant {t.tenant_id.slice(0, 10)}…</div>
                    </td>
                    <td style={tdStyle}>{t.category}</td>
                    <td style={tdStyle}>{t.priority}</td>
                    <td style={tdStyle}>
                      <span style={{ display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: st.bg, color: st.fg }}>
                        {t.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td style={tdStyle}>
                      <span style={{ display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: sla.bg, color: sla.fg }}>
                        {sla.label}
                      </span>
                    </td>
                    <td style={tdStyle}>{t.created_at ? new Date(t.created_at).toLocaleDateString() : "—"}</td>
                    <td style={tdStyle}>
                      <a href={"/platform/tickets/" + t.id} style={{ color: "#5b5cf0", fontWeight: 600, textDecoration: "none", fontSize: 12 }}>
                        Open →
                      </a>
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

function SummaryCard({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18 }}>
      <div style={{ width: 8, height: 8, borderRadius: 4, background: accent, marginBottom: 10 }} />
      <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: "#17213a", marginTop: 4 }}>{value}</div>
    </div>
  );
}

const selectStyle: React.CSSProperties = { padding: "11px 14px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, background: "#fff", minWidth: 160 };
const thStyle: React.CSSProperties = { textAlign: "left", padding: "12px 16px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5" };
const tdStyle: React.CSSProperties = { padding: "13px 16px", color: "#4b5563", verticalAlign: "top" };
'''

TARGET.write_text(CONTENT, encoding="utf-8")
print(f"File saved: {TARGET.stat().st_size} bytes")