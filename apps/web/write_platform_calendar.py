"""Write the platform calendar page."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "platform" / "calendar" / "page.tsx"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = '''"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function CalendarPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [data, setData] = useState<any>(null);
  const [followUps, setFollowUps] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<any>(null);

  function headers() {
    return { Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || "") };
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [c, f] = await Promise.all([
        fetch(api() + "/api/v1/platform/calendar?year=" + year + "&month=" + month, { headers: headers(), cache: "no-store" }).then(r => r.json()),
        fetch(api() + "/api/v1/platform/follow-ups", { headers: headers(), cache: "no-store" }).then(r => r.json()),
      ]);
      if (c?.detail) throw new Error(c.detail);
      setData(c);
      setFollowUps(f);
    } catch (e: any) {
      setError(e.message || "Failed to load");
    }
    setLoading(false);
  }

  useEffect(() => { void load(); }, [year, month]);

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear(year - 1); }
    else setMonth(month - 1);
  }
  function nextMonth() {
    if (month === 12) { setMonth(1); setYear(year + 1); }
    else setMonth(month + 1);
  }

  function heatTone(count: number) {
    if (count === 0) return "#fafbfd";
    if (count <= 2) return "#e9faf2";
    if (count <= 5) return "#c6f0de";
    if (count <= 10) return "#8ee0be";
    return "#5b5cf0";
  }

  const maxEvents = data ? Math.max(1, ...data.days.map((d: any) => d.total_events)) : 1;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Calendar</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Signups, activity, and things that need attention.
        </p>
      </div>

      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {/* Month nav + heatmap */}
      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginBottom: 18 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <button onClick={prevMonth} style={navBtn}>‹</button>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#17213a" }}>{MONTHS[month - 1]} {year}</div>
          <button onClick={nextMonth} style={navBtn}>›</button>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: "#75839a" }}>Loading…</div>
        ) : data ? (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4, marginBottom: 8 }}>
              {DAY_LABELS.map((d) => (
                <div key={d} style={{ textAlign: "center", fontSize: 10, color: "#8b97a9", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", padding: 4 }}>{d}</div>
              ))}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
              {/* leading blanks for the first weekday offset */}
              {Array.from({ length: data.first_day_weekday - 1 }).map((_, i) => (
                <div key={"pad" + i} />
              ))}
              {data.days.map((d: any) => {
                const tone = heatTone(d.total_events);
                const dark = d.total_events > 10;
                return (
                  <button
                    key={d.date}
                    onClick={() => setSelected(d)}
                    style={{
                      background: tone,
                      color: dark ? "#fff" : "#17213a",
                      border: "1px solid #eef1f5",
                      borderRadius: 8,
                      padding: "10px 6px",
                      minHeight: 62,
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      textAlign: "left",
                      transition: "transform 0.08s",
                    }}
                  >
                    <span style={{ fontSize: 13, fontWeight: 700 }}>
                      {d.date.slice(8, 10)}
                    </span>
                    {d.total_events > 0 && (
                      <span style={{ fontSize: 10, opacity: 0.85 }}>
                        {d.total_events} event{d.total_events === 1 ? "" : "s"}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            <div style={{ display: "flex", gap: 14, marginTop: 16, fontSize: 11, color: "#75839a", alignItems: "center", flexWrap: "wrap" }}>
              <span>Heat:</span>
              {[0, 1, 3, 6, 12].map((v) => (
                <span key={v} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ width: 14, height: 14, borderRadius: 3, background: heatTone(v), display: "inline-block" }} />
                  {v === 0 ? "0" : v === 12 ? "12+" : v}
                </span>
              ))}
            </div>
          </>
        ) : null}
      </div>

      {/* Selected day detail */}
      {selected && (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginBottom: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 15, color: "#17213a" }}>{selected.date}</h2>
            <button onClick={() => setSelected(null)} style={{ background: "transparent", border: 0, color: "#8490a4", cursor: "pointer", fontSize: 13 }}>Close</button>
          </div>
          {selected.signups.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600, marginBottom: 6 }}>Signups</div>
              {selected.signups.map((s: any) => (
                <div key={s.id} style={{ padding: "8px 0", borderBottom: "1px solid #f1f4f8" }}>
                  <a href={"/platform/tenants/" + s.id} style={{ color: "#5b5cf0", textDecoration: "none", fontWeight: 600, fontSize: 13 }}>
                    {s.name}
                  </a>
                  <span style={{ color: "#8b95a5", fontSize: 12 }}> · {s.industry}</span>
                </div>
              ))}
            </div>
          )}
          {selected.orders > 0 && <p style={{ margin: "6px 0", fontSize: 13, color: "#4b5563" }}>Orders: <b>{selected.orders}</b></p>}
          {selected.calls > 0 && <p style={{ margin: "6px 0", fontSize: 13, color: "#4b5563" }}>AI calls: <b>{selected.calls}</b></p>}
          {selected.total_events === 0 && <p style={{ margin: 0, fontSize: 13, color: "#8490a4" }}>No activity on this day.</p>}
        </div>
      )}

      {/* Follow-ups */}
      {followUps && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 }}>
          <FollowUpCard title="Inactive tenants (30d+)" accent="#e99132" items={followUps.inactive_tenants} render={(x: any) => (
            <a href={"/platform/tenants/" + x.tenant_id} style={{ color: "#5b5cf0", textDecoration: "none", fontWeight: 600, fontSize: 13 }}>{x.name}</a>
          )} sub={(x: any) => x.days_inactive + " days inactive"} />
          <FollowUpCard title="Breached SLA tickets" accent="#c74646" items={followUps.breached_tickets} render={(x: any) => (
            <a href={"/platform/tickets/" + x.ticket_id} style={{ color: "#5b5cf0", textDecoration: "none", fontWeight: 600, fontSize: 13 }}>{x.subject}</a>
          )} sub={(x: any) => x.category + " · due " + (x.due_at ? new Date(x.due_at).toLocaleDateString() : "—")} />
          <FollowUpCard title="Stuck orders (4h+)" accent="#8a62ed" items={followUps.stuck_orders} render={(x: any) => (
            <span style={{ fontWeight: 600, fontSize: 13, color: "#17213a" }}>Order {x.order_id.slice(0, 8)}</span>
          )} sub={(x: any) => x.status + " · " + x.age_hours + "h old"} />
        </div>
      )}
    </div>
  );
}

function FollowUpCard({ title, accent, items, render, sub }: any) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span style={{ width: 8, height: 8, borderRadius: 4, background: accent, display: "inline-block" }} />
        <h3 style={{ margin: 0, fontSize: 13, color: "#17213a" }}>{title}</h3>
        <span style={{ marginLeft: "auto", fontSize: 12, color: "#8490a4", fontWeight: 700 }}>{items.length}</span>
      </div>
      {items.length === 0 ? (
        <p style={{ margin: 0, fontSize: 12, color: "#8490a4" }}>Nothing here — good.</p>
      ) : (
        <div style={{ maxHeight: 260, overflowY: "auto" }}>
          {items.map((x: any, i: number) => (
            <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid #f1f4f8" }}>
              {render(x)}
              <div style={{ fontSize: 11, color: "#8b95a5", marginTop: 2 }}>{sub(x)}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const navBtn: React.CSSProperties = { background: "#fff", border: "1px solid #d7dce5", width: 38, height: 38, borderRadius: 10, fontSize: 18, cursor: "pointer", color: "#17213a" };
'''

TARGET.write_text(CONTENT, encoding="utf-8")
print(f"File saved: {TARGET.stat().st_size} bytes")