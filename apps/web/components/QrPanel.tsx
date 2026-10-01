"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type QrItem = {
  id: string;
  tenant_id: string;
  kind: "business" | "context" | "campaign";
  label: string;
  token: string;
  scans: number;
  context_type: string | null;
  context_value: string | null;
  campaign_id: string | null;
  created_at: string | null;
  url: string;
};

type Analytics = {
  days: number;
  total_scans: number;
  per_day: { date: string; scans: number }[];
  by_kind: Record<string, number>;
  by_context: { type: string; value: string; scans: number }[];
  by_campaign: { campaign_id: string; scans: number }[];
};

const CONTEXT_TYPES = [
  "table",
  "room",
  "seat",
  "counter",
  "product",
  "property",
  "department",
  "other",
];

export default function QrPanel({ tenantId, token }: { tenantId: string; token: string }) {
  const [items, setItems] = useState<QrItem[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [creating, setCreating] = useState(false);

  // create form state
  const [kind, setKind] = useState<"business" | "context" | "campaign">("business");
  const [label, setLabel] = useState("Business QR");
  const [contextType, setContextType] = useState("table");
  const [contextValue, setContextValue] = useState("");
  const [campaignId, setCampaignId] = useState("");

  const authHeaders = () => ({ Authorization: "Bearer " + token });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try {
      x = JSON.parse(raw);
    } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function jsend(path: string, method: string, body?: any) {
    const r = await fetch(api() + path, {
      method,
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    const raw = await r.text();
    let x: any = {};
    try {
      x = JSON.parse(raw);
    } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [listRes, analyticsRes] = await Promise.all([
        jget(`/api/v1/tenants/${tenantId}/qr`),
        jget(`/api/v1/tenants/${tenantId}/qr-analytics?days=30`),
      ]);
      setItems(listRes.items || []);
      setAnalytics(analyticsRes);
    } catch (e: any) {
      setError(e.message || "Could not load QRs");
    }
    setLoading(false);
  }

  useEffect(() => {
    if (tenantId) void loadAll();
  }, [tenantId]);

  async function create() {
    setStatus("");
    setCreating(true);
    try {
      const body: any = { kind, label };
      if (kind === "context") {
        if (!contextValue.trim()) {
          setStatus("Context value is required (e.g. 5 for Table 5)");
          setCreating(false);
          return;
        }
        body.context_type = contextType;
        body.context_value = contextValue.trim();
      }
      if (kind === "campaign") {
        if (!campaignId.trim()) {
          setStatus("Campaign ID is required");
          setCreating(false);
          return;
        }
        body.campaign_id = campaignId.trim();
      }
      const res = await jsend(`/api/v1/tenants/${tenantId}/qr`, "POST", body);
      setStatus(`Created QR: ${res.label}`);
      setContextValue("");
      setCampaignId("");
      await loadAll();
    } catch (e: any) {
      setStatus(e.message || "Could not create QR");
    }
    setCreating(false);
  }

  async function remove(id: string, label: string) {
    if (!confirm(`Delete QR "${label}"? Scans already recorded are kept.`)) return;
    try {
      await jsend(`/api/v1/tenants/${tenantId}/qr/${id}`, "DELETE");
      setStatus(`Deleted: ${label}`);
      await loadAll();
    } catch (e: any) {
      setStatus(e.message || "Could not delete QR");
    }
  }

  async function downloadPng(item: QrItem) {
    try {
      const r = await fetch(
        api() + `/api/v1/tenants/${tenantId}/qr/${item.id}/png?size=600`,
        { headers: authHeaders() }
      );
      if (!r.ok) throw new Error("Could not fetch QR image");
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `qr-${item.kind}-${item.token.slice(0, 8)}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setStatus(e.message || "Download failed");
    }
  }

  function copyUrl(item: QrItem) {
    navigator.clipboard.writeText(item.url);
    setStatus(`Copied: ${item.url}`);
  }

  function maxScans(): number {
    if (!analytics?.per_day?.length) return 1;
    return Math.max(1, ...analytics.per_day.map((d) => d.scans));
  }

  return (
    <section className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2>🔳 QR Codes</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            Business QR opens your PWA. Context QR identifies a table, room, or seat. Campaign QR tracks
            ads and flyers.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn-ghost" onClick={loadAll} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && (
        <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>
      )}

      {/* --- Create form --- */}
      <div style={{ marginTop: 20, padding: 16, background: "#f9fafc", borderRadius: 12, border: "1px solid #e8ecf3" }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>Create a new QR</h3>

        <div className="grid" style={{ gap: 12 }}>
          <label>
            Type
            <select value={kind} onChange={(e) => setKind(e.target.value as any)}>
              <option value="business">Business — opens full PWA</option>
              <option value="context">Context — table / room / seat</option>
              <option value="campaign">Campaign — ad / flyer tracking</option>
            </select>
          </label>

          <label>
            Label
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Front door, Table 5, Diwali flyer"
            />
          </label>

          {kind === "context" && (
            <>
              <label>
                Context type
                <select value={contextType} onChange={(e) => setContextType(e.target.value)}>
                  {CONTEXT_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Context value
                <input
                  value={contextValue}
                  onChange={(e) => setContextValue(e.target.value)}
                  placeholder="5 (for Table 5) or 204 (for Room 204)"
                />
              </label>
            </>
          )}

          {kind === "campaign" && (
            <label>
              Campaign ID
              <input
                value={campaignId}
                onChange={(e) => setCampaignId(e.target.value)}
                placeholder="diwali-2026, google-ads-oct"
              />
            </label>
          )}

          <button
            className="btn-primary"
            onClick={create}
            disabled={creating}
            style={{ justifySelf: "start", padding: "11px 20px" }}
          >
            {creating ? "Creating…" : "Create QR"}
          </button>
        </div>
      </div>

      {/* --- List --- */}
      <div style={{ marginTop: 24 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
          Your QRs ({items.length})
        </h3>

        {items.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No QRs yet</h3>
            <p>Create your first QR above to start tracking scans.</p>
          </div>
        )}

        {items.map((item) => (
          <article
            key={item.id}
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
                  <strong style={{ fontSize: 15 }}>{item.label}</strong>
                  <span
                    className={
                      "badge " +
                      (item.kind === "business"
                        ? "badge-blue"
                        : item.kind === "context"
                        ? "badge-purple"
                        : "badge-orange")
                    }
                  >
                    {item.kind}
                  </span>
                  {item.context_type && (
                    <span className="badge badge-grey">
                      {item.context_type}: {item.context_value}
                    </span>
                  )}
                  {item.campaign_id && (
                    <span className="badge badge-grey">campaign: {item.campaign_id}</span>
                  )}
                </div>
                <p
                  style={{
                    margin: "6px 0 0",
                    fontFamily: "monospace",
                    fontSize: 11,
                    color: "#75839a",
                    wordBreak: "break-all",
                  }}
                >
                  {item.url}
                </p>
                <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                  <strong style={{ color: "#17213a" }}>{item.scans}</strong> total scans
                  {item.created_at && (
                    <>
                      {" · "}created {new Date(item.created_at).toLocaleDateString()}
                    </>
                  )}
                </p>
              </div>

              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button className="btn-ghost" onClick={() => downloadPng(item)}>
                  Download PNG
                </button>
                <button className="btn-ghost" onClick={() => copyUrl(item)}>
                  Copy URL
                </button>
                <button
                  className="btn-ghost"
                  style={{ color: "#c74646", borderColor: "#f0c6c6" }}
                  onClick={() => remove(item.id, item.label)}
                >
                  Delete
                </button>
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* --- Analytics --- */}
      {analytics && (
        <div style={{ marginTop: 24, paddingTop: 20, borderTop: "1px solid #eef1f5" }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
            Scan analytics · last {analytics.days} days
          </h3>

          <div className="grid" style={{ gap: 12, marginBottom: 20 }}>
            <div className="stat">
              <span className="stat-label">Total scans</span>
              <span className="stat-value">{analytics.total_scans}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Business</span>
              <span className="stat-value">{analytics.by_kind.business || 0}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Context</span>
              <span className="stat-value">{analytics.by_kind.context || 0}</span>
            </div>
            <div className="stat">
              <span className="stat-label">Campaign</span>
              <span className="stat-value">{analytics.by_kind.campaign || 0}</span>
            </div>
          </div>

          {/* 30-day bar chart */}
          {analytics.per_day.length > 0 && (
            <div style={{ marginBottom: 20 }}>
              <p style={{ margin: "0 0 8px", fontSize: 11, color: "#75839a", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                Scans per day
              </p>
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-end",
                  gap: 3,
                  height: 80,
                  padding: "8px 0",
                  background: "#fafbfd",
                  borderRadius: 8,
                }}
              >
                {analytics.per_day.map((d) => (
                  <div
                    key={d.date}
                    title={`${d.date}: ${d.scans} scans`}
                    style={{
                      flex: 1,
                      height: `${Math.max(4, (d.scans / maxScans()) * 100)}%`,
                      background: "linear-gradient(180deg, #5b5cf0, #7159f7)",
                      borderRadius: 3,
                      minWidth: 4,
                    }}
                  />
                ))}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#98a2b4", marginTop: 4 }}>
                <span>{analytics.per_day[0]?.date}</span>
                <span>{analytics.per_day[analytics.per_day.length - 1]?.date}</span>
              </div>
            </div>
          )}

          {/* Top contexts */}
          {analytics.by_context.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <p style={{ margin: "0 0 8px", fontSize: 11, color: "#75839a", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                Top contexts
              </p>
              {analytics.by_context.slice(0, 10).map((c) => (
                <div
                  key={`${c.type}-${c.value}`}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "6px 0",
                    fontSize: 13,
                    borderBottom: "1px solid #f1f4f8",
                  }}
                >
                  <span>
                    <strong>{c.type}</strong> · {c.value}
                  </span>
                  <span style={{ color: "#75839a" }}>{c.scans} scans</span>
                </div>
              ))}
            </div>
          )}

          {/* Top campaigns */}
          {analytics.by_campaign.length > 0 && (
            <div>
              <p style={{ margin: "0 0 8px", fontSize: 11, color: "#75839a", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
                Top campaigns
              </p>
              {analytics.by_campaign.slice(0, 10).map((c) => (
                <div
                  key={c.campaign_id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    padding: "6px 0",
                    fontSize: 13,
                    borderBottom: "1px solid #f1f4f8",
                  }}
                >
                  <span>{c.campaign_id}</span>
                  <span style={{ color: "#75839a" }}>{c.scans} scans</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {status && (
        <p
          aria-live="polite"
          style={{ marginTop: 16, fontSize: 12, color: "#1aa76c" }}
        >
          {status}
        </p>
      )}
    </section>
  );
}