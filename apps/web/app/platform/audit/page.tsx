"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type AuditRow = {
  id: string;
  tenant_id: string | null;
  actor_id: string | null;
  action: string;
  target_type: string;
  target_id: string;
  detail: Record<string, any>;
  request_id: string | null;
  created_at: string | null;
};

export default function AuditLogPage() {
  const [items, setItems] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [tenantFilter, setTenantFilter] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [limit, setLimit] = useState(100);

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) { window.location.href = "/login"; return; }
    setLoading(true);
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    if (actionFilter) params.set("action", actionFilter);
    if (tenantFilter) params.set("tenant_id", tenantFilter);
    fetch(api() + "/api/v1/platform/audit-log?" + params.toString(), {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
    })
      .then((r) => {
        if (r.status === 401 || r.status === 403) { window.location.href = "/login"; throw new Error("auth"); }
        return r.json();
      })
      .then((x) => { setItems(x.items || []); setLoading(false); })
      .catch((e) => { if (e.message !== "auth") setError(e.message || "Failed to load"); setLoading(false); });
  }, [actionFilter, tenantFilter, limit]);

  function actionTone(action: string) {
    if (action.startsWith("payment.")) return { bg: "#e9faf2", fg: "#1d9c68" };
    if (action.startsWith("loyalty.")) return { bg: "#f0eaff", fg: "#7a55d6" };
    if (action.startsWith("platform.")) return { bg: "#edf2ff", fg: "#566ce1" };
    if (action.startsWith("qr.")) return { bg: "#fff0df", fg: "#e99132" };
    if (action.startsWith("review.")) return { bg: "#fff9e6", fg: "#c98c1a" };
    if (action.startsWith("whatsapp.")) return { bg: "#e5f8f8", fg: "#20a7a0" };
    if (action.startsWith("error")) return { bg: "#fff1f1", fg: "#c74646" };
    return { bg: "#f2f4f8", fg: "#6b7686" };
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Audit Log</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Every money, reward, permission, and platform action is recorded here.
        </p>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <input
          placeholder="Filter by action (e.g. payment.captured)"
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          style={{ flex: 1, minWidth: 240, padding: "11px 14px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, outline: "none" }}
        />
        <input
          placeholder="Filter by tenant ID"
          value={tenantFilter}
          onChange={(e) => setTenantFilter(e.target.value)}
          style={{ flex: 1, minWidth: 240, padding: "11px 14px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, outline: "none" }}
        />
        <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} style={{ padding: "11px 14px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, background: "#fff" }}>
          <option value={50}>50 rows</option>
          <option value={100}>100 rows</option>
          <option value={250}>250 rows</option>
          <option value={500}>500 rows</option>
        </select>
      </div>

      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>
      ) : items.length === 0 ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px dashed #dbe1ea", borderRadius: 14 }}>
          <h3 style={{ margin: "0 0 6px", color: "#17213a", fontSize: 15 }}>No audit events</h3>
          <p style={{ margin: 0, fontSize: 13 }}>Actions will appear here as tenants use the platform.</p>
        </div>
      ) : (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#fafbfd" }}>
              <tr>
                <th style={thStyle}>Action</th>
                <th style={thStyle}>Target</th>
                <th style={thStyle}>Tenant</th>
                <th style={thStyle}>Actor</th>
                <th style={thStyle}>When</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => {
                const tone = actionTone(row.action);
                const open = expanded === row.id;
                return (
                  <>
                    <tr key={row.id} style={{ borderTop: "1px solid #f1f4f8" }}>
                      <td style={tdStyle}>
                        <span style={{ display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: tone.bg, color: tone.fg }}>
                          {row.action}
                        </span>
                      </td>
                      <td style={tdStyle}>
                        <div style={{ color: "#17213a" }}>{row.target_type}</div>
                        <div style={{ color: "#8b95a5", fontSize: 11, fontFamily: "monospace" }}>{row.target_id.slice(0, 20)}</div>
                      </td>
                      <td style={tdStyle}>{row.tenant_id ? row.tenant_id.slice(0, 12) + "…" : "—"}</td>
                      <td style={tdStyle}>{row.actor_id ? row.actor_id.slice(0, 12) + "…" : "system"}</td>
                      <td style={tdStyle}>{row.created_at ? new Date(row.created_at).toLocaleString() : "—"}</td>
                      <td style={tdStyle}>
                        {row.detail && Object.keys(row.detail).length > 0 && (
                          <button
                            onClick={() => setExpanded(open ? null : row.id)}
                            style={{ background: "transparent", border: 0, color: "#5b5cf0", fontWeight: 600, fontSize: 12, cursor: "pointer", padding: 4 }}
                          >
                            {open ? "Hide" : "Details"}
                          </button>
                        )}
                      </td>
                    </tr>
                    {open && (
                      <tr key={row.id + "-expanded"} style={{ background: "#fafbfd" }}>
                        <td colSpan={6} style={{ padding: 16 }}>
                          <pre style={{ margin: 0, fontSize: 11, color: "#4b5563", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                            {JSON.stringify(row.detail, null, 2)}
                          </pre>
                          {row.request_id && (
                            <div style={{ marginTop: 10, fontSize: 11, color: "#8b95a5" }}>
                              request_id: <code>{row.request_id}</code>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </>
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
