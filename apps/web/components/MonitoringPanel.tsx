"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type CurrentItem = {
  status: string;
  detail: Record<string, any>;
  at: string | null;
  latency_ms: number | null;
};

type ActionRow = {
  id: string;
  component: string;
  action: string;
  outcome: string;
  detail: string | null;
  created_at: string | null;
};

type AlertRow = {
  id: string;
  severity: string;
  component: string;
  title: string;
  body: string;
  email_sent: boolean;
  whatsapp_sent: boolean;
  delivery_error: string | null;
  created_at: string | null;
};

type BackupRow = {
  id: string;
  source_path: string;
  backup_path: string;
  size_bytes: number;
  ok: boolean;
  error: string | null;
  created_at: string | null;
};

const CATEGORIES: { key: string; label: string; hint: string }[] = [
  { key: "backend",      label: "Backend",      hint: "API process is running" },
  { key: "database",     label: "Database",     hint: "DB reachable" },
  { key: "email_poller", label: "Email poller", hint: "Polls mailboxes every 60s" },
  { key: "whatsapp",     label: "WhatsApp",     hint: "Channels connected" },
  { key: "ai_provider",  label: "AI providers", hint: "Credentials configured" },
  { key: "disk",         label: "Disk",         hint: "Free space" },
  { key: "backup",       label: "Backup",       hint: "Last DB snapshot" },
];

const STATUS_COLOUR: Record<string, string> = {
  ok: "#1d9c68",
  degraded: "#c98c1a",
  down: "#c74646",
  unknown: "#8b95a5",
};

const STATUS_BG: Record<string, string> = {
  ok: "#e9faf2",
  degraded: "#fff9e6",
  down: "#fff1f1",
  unknown: "#f1f4f8",
};

function fmtAgo(iso: string | null): string {
  if (!iso) return "never";
  const u = iso.endsWith("Z") ? iso : iso + "Z";
  const seconds = Math.floor((Date.now() - new Date(u).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function fmtBytes(n: number): string {
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  if (n < 1024 * 1024 * 1024) return (n / (1024 * 1024)).toFixed(1) + " MB";
  return (n / (1024 * 1024 * 1024)).toFixed(2) + " GB";
}

export default function MonitoringPanel() {
  const [current, setCurrent] = useState<Record<string, CurrentItem>>({});
  const [actions, setActions] = useState<ActionRow[]>([]);
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [backups, setBackups] = useState<BackupRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  const authHeaders = () => ({
    "Content-Type": "application/json",
    Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || ""),
  });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll() {
    setError("");
    try {
      const [c, a, al, b] = await Promise.all([
        jget("/api/v1/platform/monitoring/current"),
        jget("/api/v1/platform/monitoring/actions?limit=50").catch(() => ({ items: [] })),
        jget("/api/v1/platform/monitoring/alerts?limit=50").catch(() => ({ items: [] })),
        jget("/api/v1/platform/monitoring/backups?limit=20").catch(() => ({ items: [] })),
      ]);
      setCurrent(c || {});
      setActions(a.items || []);
      setAlerts(al.items || []);
      setBackups(b.items || []);
      setLastRefresh(new Date());
    } catch (e: any) {
      setError(e.message || "Could not load monitoring data");
    }
    setLoading(false);
  }

  useEffect(() => {
    void loadAll();
    const iv = setInterval(() => { void loadAll(); }, 30000);
    return () => clearInterval(iv);
  }, []);

  const healthyCount = CATEGORIES.filter((c) => current[c.key]?.status === "ok").length;
  const overallOK = healthyCount === CATEGORIES.length;

  return (
    <div>
      {error && <p style={{ color: "#b00", marginBottom: 16 }}>{error}</p>}

      {/* Top banner */}
      <div
        style={{
          padding: "14px 18px",
          borderRadius: 12,
          marginBottom: 20,
          background: overallOK ? "#e9faf2" : "#fff9e6",
          border: overallOK ? "1px solid #b3e5cd" : "1px solid #f2dca0",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 18 }}>{overallOK ? "✅" : "⚠️"}</span>
          <strong style={{ fontSize: 14, color: "#17213a" }}>
            {overallOK ? "All systems operational" : `${healthyCount} of ${CATEGORIES.length} components healthy`}
          </strong>
        </div>
        <button className="btn-ghost" onClick={loadAll} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {/* Status grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 12,
          marginBottom: 24,
        }}
      >
        {CATEGORIES.map((cat) => {
          const item = current[cat.key];
          const status = item?.status || "unknown";
          return (
            <div
              key={cat.key}
              style={{
                background: "#fff",
                border: "1px solid #e8ecf3",
                borderRadius: 12,
                padding: 14,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <strong style={{ fontSize: 13, color: "#17213a" }}>{cat.label}</strong>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "3px 8px",
                    borderRadius: 20,
                    background: STATUS_BG[status] || STATUS_BG.unknown,
                    color: STATUS_COLOUR[status] || STATUS_COLOUR.unknown,
                  }}
                >
                  {status.toUpperCase()}
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 11, color: "#8b95a5", marginBottom: 8 }}>
                {cat.hint}
              </p>
              <p style={{ margin: 0, fontSize: 11, color: "#75839a" }}>
                {item?.at ? <>checked {fmtAgo(item.at)}</> : "no data"}
                {item?.latency_ms != null ? <> · {item.latency_ms}ms</> : null}
              </p>
              {item?.detail && Object.keys(item.detail).length > 0 && (
                <pre
                  style={{
                    margin: "8px 0 0",
                    fontSize: 10.5,
                    color: "#4a5875",
                    fontFamily: "monospace",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                    maxHeight: 80,
                    overflowY: "auto",
                  }}
                >
                  {JSON.stringify(item.detail, null, 2)}
                </pre>
              )}
            </div>
          );
        })}
      </div>

      {/* Recent self-heal actions */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 12, padding: 18, marginBottom: 20 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "#17213a" }}>
          Recent auto-recovery actions
        </h3>
        {actions.length === 0 ? (
          <p style={{ margin: 0, color: "#75839a", fontSize: 13 }}>
            No self-heal actions yet. The system has nothing to fix — good.
          </p>
        ) : (
          <div style={{ maxHeight: 260, overflowY: "auto" }}>
            {actions.map((a) => (
              <div
                key={a.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: 12,
                  padding: "8px 0",
                  fontSize: 12.5,
                  borderBottom: "1px solid #f1f4f8",
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <span
                    style={{
                      display: "inline-block",
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 12,
                      marginRight: 8,
                      background: a.outcome === "success" ? "#e9faf2" : a.outcome === "failed" ? "#fff1f1" : "#f1f4f8",
                      color: a.outcome === "success" ? "#1d9c68" : a.outcome === "failed" ? "#c74646" : "#8b95a5",
                    }}
                  >
                    {a.outcome}
                  </span>
                  <strong style={{ color: "#17213a" }}>{a.component}</strong>
                  <span style={{ color: "#75839a" }}> · {a.action}</span>
                  {a.detail && <span style={{ color: "#98a2b4" }}> — {a.detail}</span>}
                </div>
                <span style={{ color: "#98a2b4", fontSize: 11, flexShrink: 0 }}>{fmtAgo(a.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Alerts */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 12, padding: 18, marginBottom: 20 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "#17213a" }}>
          Recent alerts
        </h3>
        {alerts.length === 0 ? (
          <p style={{ margin: 0, color: "#75839a", fontSize: 13 }}>
            No alerts. Nothing needs your attention.
          </p>
        ) : (
          <div style={{ maxHeight: 260, overflowY: "auto" }}>
            {alerts.map((a) => (
              <div
                key={a.id}
                style={{
                  padding: "10px 12px",
                  borderRadius: 8,
                  marginBottom: 8,
                  background: a.severity === "critical" ? "#fff1f1" : a.severity === "warning" ? "#fff9e6" : "#f1f4f8",
                  border: a.severity === "critical" ? "1px solid #f2b8b8" : a.severity === "warning" ? "1px solid #f2dca0" : "1px solid #e8ecf3",
                  fontSize: 12.5,
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <strong style={{ color: "#17213a" }}>{a.title}</strong>
                  <span style={{ color: "#98a2b4", fontSize: 11 }}>{fmtAgo(a.created_at)}</span>
                </div>
                <p style={{ margin: "4px 0 0", color: "#4a5875" }}>{a.body}</p>
                <p style={{ margin: "4px 0 0", fontSize: 11, color: "#98a2b4" }}>
                  Component: {a.component} · Email: {a.email_sent ? "sent" : "pending"} · WhatsApp: {a.whatsapp_sent ? "sent" : "pending"}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Backups */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 12, padding: 18 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "#17213a" }}>
          Database backups (last 20)
        </h3>
        {backups.length === 0 ? (
          <p style={{ margin: 0, color: "#75839a", fontSize: 13 }}>
            No backups yet. First one runs at app startup.
          </p>
        ) : (
          <div style={{ maxHeight: 260, overflowY: "auto" }}>
            {backups.map((b) => (
              <div
                key={b.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 12,
                  padding: "8px 0",
                  fontSize: 12.5,
                  borderBottom: "1px solid #f1f4f8",
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <span
                    style={{
                      display: "inline-block",
                      fontSize: 10,
                      fontWeight: 700,
                      padding: "2px 8px",
                      borderRadius: 12,
                      marginRight: 8,
                      background: b.ok ? "#e9faf2" : "#fff1f1",
                      color: b.ok ? "#1d9c68" : "#c74646",
                    }}
                  >
                    {b.ok ? "ok" : "fail"}
                  </span>
                  <span style={{ fontFamily: "monospace", fontSize: 11.5, color: "#4a5875" }}>
                    {b.backup_path.split(/[\\/]/).pop()}
                  </span>
                  <span style={{ color: "#75839a" }}> · {fmtBytes(b.size_bytes)}</span>
                </div>
                <span style={{ color: "#98a2b4", fontSize: 11, flexShrink: 0 }}>{fmtAgo(b.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {lastRefresh && (
        <p style={{ marginTop: 20, fontSize: 11, color: "#98a2b4", textAlign: "right" }}>
          Auto-refreshes every 30s · last update {lastRefresh.toLocaleTimeString()}
        </p>
      )}
    </div>
  );
}