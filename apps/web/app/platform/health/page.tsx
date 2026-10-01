"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Health = {
  status: string;
  service?: string;
  time?: string;
  commit?: string;
  checks?: Record<string, any>;
};

export default function HealthPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [turn, setTurn] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const h = await fetch(api() + "/health", { cache: "no-store" });
      if (!h.ok) throw new Error("API returned " + h.status);
      setHealth(await h.json());

      try {
        const t = await fetch(api() + "/api/v1/health/turn", {
          headers: { Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || "") },
          cache: "no-store",
        });
        if (t.ok) setTurn(await t.json());
      } catch {
        setTurn(null);
      }

      setLastChecked(new Date());
    } catch (e: any) {
      setError(e.message || "Failed to reach API");
    }
    setLoading(false);
  }

  useEffect(() => { void load(); }, []);

  const statusColor = (ok: boolean | undefined) => ok === true ? "#1d9c68" : ok === false ? "#c74646" : "#8490a4";
  const statusBg = (ok: boolean | undefined) => ok === true ? "#e9faf2" : ok === false ? "#fff1f1" : "#f2f4f8";

  return (
    <div>
      <div style={{ marginBottom: 24, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Health</h1>
          <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
            Live system status. {lastChecked ? "Last checked " + lastChecked.toLocaleTimeString() : "Not yet checked."}
          </p>
        </div>
        <button onClick={load} disabled={loading} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: loading ? "wait" : "pointer" }}>
          {loading ? "Checking…" : "Refresh"}
        </button>
      </div>

      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {health && (
        <>
          {/* Big status banner */}
          <div
            style={{
              background: health.status === "ok" ? "linear-gradient(135deg,#1d9c68,#20aa72)" : health.status === "degraded" ? "linear-gradient(135deg,#e99132,#c98c1a)" : "linear-gradient(135deg,#c74646,#b03030)",
              color: "#fff",
              borderRadius: 14,
              padding: 24,
              marginBottom: 18,
            }}
          >
            <div style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", opacity: 0.85, fontWeight: 700 }}>Overall status</div>
            <div style={{ fontSize: 32, fontWeight: 700, margin: "8px 0 4px", textTransform: "capitalize" }}>{health.status}</div>
            <div style={{ fontSize: 13, opacity: 0.85 }}>
              {health.service || "ai-growth-os-api"} · commit {health.commit || "unknown"} · {health.time ? new Date(health.time).toLocaleString() : ""}
            </div>
          </div>

          {/* Checks grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14, marginBottom: 18 }}>
            {Object.entries(health.checks || {}).map(([name, check]: any) => {
              const ok = check?.ok;
              return (
                <div key={name} style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                    <span style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700 }}>{name}</span>
                    <span style={{ display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: statusBg(ok), color: statusColor(ok) }}>
                      {ok === true ? "OK" : ok === false ? "FAIL" : "—"}
                    </span>
                  </div>
                  {check?.error && <p style={{ margin: "0 0 6px", fontSize: 12, color: "#c74646", wordBreak: "break-word" }}>{check.error}</p>}
                  {check?.note && <p style={{ margin: "0 0 6px", fontSize: 11, color: "#8490a4", fontStyle: "italic" }}>{check.note}</p>}
                  {name === "turn" && (
                    <div style={{ fontSize: 12, color: "#4b5563", marginTop: 6 }}>
                      <div>Primary: <b>{check.primary}</b></div>
                      <div>Fallback: <b>{check.fallback || "none"}</b></div>
                      <div>Cloudflare: {check.cloudflare_configured ? "🟢 configured" : "🔴 not configured"}</div>
                      <div>Metered: {check.metered_configured ? "🟢 configured" : "🔴 not configured"}</div>
                    </div>
                  )}
                  {name === "encryption" && (
                    <div style={{ fontSize: 12, color: "#4b5563", marginTop: 6 }}>
                      <div>WhatsApp key: {check.whatsapp_key_set ? "🟢 set" : "🔴 missing"}</div>
                      <div>Integration key: {check.integration_key_set ? "🟢 set" : "🔴 missing"}</div>
                    </div>
                  )}
                  {name === "auth_rate_limit" && (
                    <div style={{ fontSize: 12, color: "#4b5563", marginTop: 6 }}>
                      <div>Active buckets: <b>{check.active_buckets}</b></div>
                      <div>Tracked keys: <b>{check.tracked_keys}</b></div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* TURN config block */}
          {turn && (
            <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20 }}>
              <h2 style={{ margin: "0 0 12px", fontSize: 15, color: "#17213a" }}>TURN configuration</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, fontSize: 13 }}>
                <div>Primary: <b>{turn.primary}</b></div>
                <div>Fallback: <b>{turn.fallback || "none"}</b></div>
                <div>Cloudflare: <b style={{ color: turn.cloudflare_configured ? "#1d9c68" : "#8490a4" }}>{turn.cloudflare_configured ? "configured" : "not set"}</b></div>
                <div>Metered: <b style={{ color: turn.metered_configured ? "#1d9c68" : "#8490a4" }}>{turn.metered_configured ? "configured" : "not set"}</b></div>
              </div>
            </div>
          )}
        </>
      )}

      {!loading && !health && !error && (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px dashed #dbe1ea", borderRadius: 14 }}>
          <h3 style={{ margin: "0 0 6px", color: "#17213a", fontSize: 15 }}>API unreachable</h3>
          <p style={{ margin: 0, fontSize: 13 }}>Is uvicorn running on {api()}?</p>
        </div>
      )}
    </div>
  );
}
