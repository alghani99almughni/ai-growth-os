"use client";
import { useEffect, useState } from "react";
import { getActiveTenantId, getActiveToken } from "../../../lib/activeTenant";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type Row = {
  weekday: number;
  open_time: string;
  close_time: string;
  is_closed: boolean;
  slot_interval_minutes: number;
};

const DEFAULT_ROWS: Row[] = DAYS.map((_, i) => ({
  weekday: i,
  open_time: "09:00",
  close_time: i === 6 ? "13:00" : "18:00",
  is_closed: i === 6,
  slot_interval_minutes: 30,
}));

export default function BusinessHoursPage() {
  const [tenantId, setTenantId] = useState("");
  const [token, setToken] = useState("");
  const [rows, setRows] = useState<Row[]>(DEFAULT_ROWS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setTenantId(getActiveTenantId());
    setToken(getActiveToken());
  }, []);

  useEffect(() => {
    if (!tenantId || !token) return;
    void load();
  }, [tenantId, token]);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const r = await fetch(`${api()}/api/v1/tenants/${tenantId}/business-hours`, {
        headers: { Authorization: "Bearer " + token },
        cache: "no-store",
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Load failed");
      const items = (x.items || []).map((it: any) => ({
        weekday: it.weekday,
        open_time: it.open_time,
        close_time: it.close_time,
        is_closed: it.is_closed,
        slot_interval_minutes: it.slot_interval_minutes || 30,
      }));
      // Ensure 7 rows, sorted by weekday
      const byDay: Record<number, Row> = {};
      for (const it of items) byDay[it.weekday] = it;
      const merged: Row[] = [];
      for (let i = 0; i < 7; i++) merged.push(byDay[i] || DEFAULT_ROWS[i]);
      setRows(merged);
    } catch (e: any) {
      setError(e.message || "Could not load business hours");
    }
    setLoading(false);
  }

  function upd(i: number, patch: Partial<Row>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  async function save() {
    setSaving(true);
    setStatus("");
    setError("");
    try {
      const r = await fetch(`${api()}/api/v1/tenants/${tenantId}/business-hours`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({
          items: rows.map((row) => ({
            weekday: row.weekday,
            open_time: row.is_closed ? "09:00" : row.open_time,
            close_time: row.is_closed ? "18:00" : row.close_time,
            is_closed: row.is_closed,
            slot_interval_minutes: row.slot_interval_minutes || 30,
          })),
        }),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Save failed");
      setStatus("Business hours saved.");
    } catch (e: any) {
      setError(e.message || "Could not save business hours");
    }
    setSaving(false);
  }

  if (!tenantId || !token) {
    return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
          Business hours
        </h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          When the business is open. Bookings, AI voice, and the customer PWA all read these hours.
        </p>
      </div>

      {error && <p style={{ color: "#b00", marginBottom: 12 }}>{error}</p>}
      {status && <p style={{ color: "#1aa76c", marginBottom: 12, fontSize: 13 }}>{status}</p>}

      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: "#75839a" }}>Loading…</div>
      ) : (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24, maxWidth: 720 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                <th style={th}>Day</th>
                <th style={th}>Open</th>
                <th style={th}>Close</th>
                <th style={{ ...th, textAlign: "center" }}>Closed</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row.weekday} style={{ borderTop: "1px solid #f1f4f8" }}>
                  <td style={td}>{DAYS[row.weekday]}</td>
                  <td style={td}>
                    <input
                      type="time"
                      value={row.open_time}
                      disabled={row.is_closed}
                      onChange={(e) => upd(i, { open_time: e.target.value })}
                      style={inp}
                    />
                  </td>
                  <td style={td}>
                    <input
                      type="time"
                      value={row.close_time}
                      disabled={row.is_closed}
                      onChange={(e) => upd(i, { close_time: e.target.value })}
                      style={inp}
                    />
                  </td>
                  <td style={{ ...td, textAlign: "center" }}>
                    <input
                      type="checkbox"
                      checked={row.is_closed}
                      onChange={(e) => upd(i, { is_closed: e.target.checked })}
                      style={{ width: "auto", margin: 0, cursor: "pointer" }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ marginTop: 20, display: "flex", gap: 12, alignItems: "center" }}>
            <button
              onClick={save}
              disabled={saving}
              style={{
                background: "linear-gradient(135deg,#5b5cf0,#7159f7)",
                color: "#fff",
                border: 0,
                padding: "11px 22px",
                borderRadius: 10,
                fontWeight: 700,
                fontSize: 13,
                cursor: saving ? "wait" : "pointer",
              }}
            >
              {saving ? "Saving…" : "Save hours"}
            </button>
            <button
              onClick={load}
              disabled={saving}
              style={{
                background: "#fff",
                color: "#17213a",
                border: "1px solid #d7dce5",
                padding: "11px 22px",
                borderRadius: 10,
                fontWeight: 600,
                fontSize: 13,
                cursor: "pointer",
              }}
            >
              Reload
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "10px 12px",
  fontSize: 11,
  color: "#8b97a9",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  fontWeight: 600,
  borderBottom: "1px solid #edf0f5",
};

const td: React.CSSProperties = {
  padding: "10px 12px",
  color: "#4b5563",
  verticalAlign: "middle",
};

const inp: React.CSSProperties = {
  padding: "8px 10px",
  border: "1px solid #d7dce5",
  borderRadius: 8,
  fontSize: 13,
  background: "#fff",
  outline: "none",
};