"""Write the enhanced calendar page with Month/Week/Day toggle."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "platform" / "calendar" / "page.tsx"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = r'''"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAY_LABELS_SHORT = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];

type View = "month" | "week" | "day";

function isoDate(d: Date) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return y + "-" + m + "-" + dd;
}

function startOfWeek(d: Date) {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const out = new Date(d);
  out.setDate(out.getDate() + diff);
  out.setHours(0, 0, 0, 0);
  return out;
}

function prettyDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "short", year: "numeric" });
}

export default function CalendarPage() {
  const [view, setView] = useState<View>("month");
  const [anchor, setAnchor] = useState<Date>(new Date());
  const [monthData, setMonthData] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [followUps, setFollowUps] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedDay, setSelectedDay] = useState<string | null>(null);

  function headers() {
    return { Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || "") };
  }

  async function loadMonth() {
    setLoading(true); setError("");
    try {
      const y = anchor.getFullYear();
      const m = anchor.getMonth() + 1;
      const [c, f] = await Promise.all([
        fetch(api() + "/api/v1/platform/calendar?year=" + y + "&month=" + m, { headers: headers(), cache: "no-store" }).then(r => r.json()),
        fetch(api() + "/api/v1/platform/follow-ups", { headers: headers(), cache: "no-store" }).then(r => r.json()),
      ]);
      if (c?.detail) throw new Error(c.detail);
      if (!c || !Array.isArray(c.days)) throw new Error("Calendar data missing.");
      setMonthData(c);
      setFollowUps(f);
    } catch (e: any) { setError(e.message || "Failed to load"); }
    setLoading(false);
  }

  async function loadRange(startIso: string, endIso: string) {
    setLoading(true); setError("");
    try {
      const r = await fetch(api() + "/api/v1/platform/calendar/events?start=" + encodeURIComponent(startIso) + "&end=" + encodeURIComponent(endIso), { headers: headers(), cache: "no-store" });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Failed");
      setEvents(x.items || []);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  useEffect(() => {
    if (view === "month") { void loadMonth(); }
    else if (view === "week") {
      const ws = startOfWeek(anchor);
      const we = new Date(ws); we.setDate(we.getDate() + 7);
      void loadRange(ws.toISOString(), we.toISOString());
    } else {
      const ds = new Date(anchor); ds.setHours(0, 0, 0, 0);
      const de = new Date(anchor); de.setHours(23, 59, 59, 999);
      void loadRange(ds.toISOString(), de.toISOString());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, anchor.getTime()]);

  function prev() {
    const n = new Date(anchor);
    if (view === "month") n.setMonth(n.getMonth() - 1);
    else if (view === "week") n.setDate(n.getDate() - 7);
    else n.setDate(n.getDate() - 1);
    setAnchor(n); setSelectedDay(null);
  }
  function next() {
    const n = new Date(anchor);
    if (view === "month") n.setMonth(n.getMonth() + 1);
    else if (view === "week") n.setDate(n.getDate() + 7);
    else n.setDate(n.getDate() + 1);
    setAnchor(n); setSelectedDay(null);
  }
  function goToday() { setAnchor(new Date()); setSelectedDay(null); }

  const rangeLabel = (() => {
    if (view === "month") return MONTHS[anchor.getMonth()] + " " + anchor.getFullYear();
    if (view === "week") {
      const ws = startOfWeek(anchor);
      const we = new Date(ws); we.setDate(we.getDate() + 6);
      return ws.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + " – " + we.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    }
    return prettyDate(isoDate(anchor));
  })();

  function heatTone(count: number) {
    if (count === 0) return "#fafbfd";
    if (count <= 2) return "#e9faf2";
    if (count <= 5) return "#c6f0de";
    if (count <= 10) return "#8ee0be";
    return "#5b5cf0";
  }

  function kindColor(kind: string) {
    if (kind === "signup") return { bg: "#edf2ff", fg: "#566ce1" };
    if (kind === "call") return { bg: "#e5f8f8", fg: "#20a7a0" };
    if (kind === "order") return { bg: "#fff0df", fg: "#e99132" };
    if (kind === "appointment") return { bg: "#f0eaff", fg: "#7a55d6" };
    return { bg: "#f2f4f8", fg: "#6b7686" };
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Calendar</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Signups, calls, orders, and appointments — month, week, and day views.
        </p>
      </div>

      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
        <button onClick={prev} style={navBtn}>‹</button>
        <button onClick={next} style={navBtn}>›</button>
        <button onClick={goToday} style={{ ...navBtn, width: "auto", padding: "0 14px", fontWeight: 700 }}>Today</button>
        <span style={{ fontSize: 16, fontWeight: 700, color: "#17213a", minWidth: 200 }}>{rangeLabel}</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4, background: "#f2f4f8", padding: 4, borderRadius: 10 }}>
          {(["month", "week", "day"] as View[]).map((v) => (
            <button key={v} onClick={() => setView(v)} style={{ border: 0, padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: "pointer", background: view === v ? "#fff" : "transparent", color: view === v ? "#17213a" : "#75839a", boxShadow: view === v ? "0 2px 6px rgba(17,24,39,0.06)" : "none", textTransform: "capitalize" }}>
              {v}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14 }}>Loading…</div>
      ) : view === "month" ? (
        <MonthView data={monthData} onSelect={setSelectedDay} selected={selectedDay} heatTone={heatTone} />
      ) : view === "week" ? (
        <WeekView anchor={anchor} events={events} kindColor={kindColor} onSelectDay={(d: Date) => { setAnchor(d); setView("day"); }} />
      ) : (
        <DayView anchor={anchor} events={events} kindColor={kindColor} />
      )}

      {selectedDay && view === "month" && (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginTop: 18 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h2 style={{ margin: 0, fontSize: 15, color: "#17213a" }}>{prettyDate(selectedDay)}</h2>
            <button onClick={() => setSelectedDay(null)} style={{ background: "transparent", border: 0, color: "#8490a4", cursor: "pointer", fontSize: 13 }}>Close</button>
          </div>
          <DayDetail day={monthData?.days.find((d: any) => d.date === selectedDay)} />
        </div>
      )}

      {followUps && view === "month" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14, marginTop: 18 }}>
          <FollowUpCard title="Inactive tenants (30d+)" accent="#e99132" items={followUps.inactive_tenants} render={(x: any) => (
            <a href={"/platform/tenants/" + x.tenant_id} style={{ color: "#5b5cf0", textDecoration: "none", fontWeight: 600, fontSize: 13 }}>{x.name}</a>
          )} sub={(x: any) => x.days_inactive + " days inactive"} />
          <FollowUpCard title="Breached SLA tickets" accent="#c74646" items={followUps.breached_tickets} render={(x: any) => (
            <a href={"/platform/tickets/" + x.ticket_id} style={{ color: "#5b5cf0", textDecoration: "none", fontWeight: 600, fontSize: 13 }}>{x.subject}</a>
          )} sub={(x: any) => x.category} />
          <FollowUpCard title="Stuck orders (4h+)" accent="#8a62ed" items={followUps.stuck_orders} render={(x: any) => (
            <span style={{ fontWeight: 600, fontSize: 13, color: "#17213a" }}>Order {x.order_id.slice(0, 8)}</span>
          )} sub={(x: any) => x.status + " · " + x.age_hours + "h old"} />
        </div>
      )}
    </div>
  );
}

function MonthView({ data, onSelect, selected, heatTone }: any) {
  if (!data) return null;
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4, marginBottom: 8 }}>
        {DAY_LABELS_SHORT.map((d: string) => (
          <div key={d} style={{ textAlign: "center", fontSize: 10, color: "#8b97a9", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", padding: 4 }}>{d}</div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 4 }}>
        {Array.from({ length: data.first_day_weekday - 1 }).map((_, i) => <div key={"pad" + i} />)}
        {data.days.map((d: any) => {
          const tone = heatTone(d.total_events);
          const dark = d.total_events > 10;
          const isSelected = selected === d.date;
          return (
            <button key={d.date} onClick={() => onSelect(d.date)} style={{ background: tone, color: dark ? "#fff" : "#17213a", border: isSelected ? "2px solid #5b5cf0" : "1px solid #eef1f5", borderRadius: 8, padding: "10px 6px", minHeight: 62, cursor: "pointer", display: "flex", flexDirection: "column", justifyContent: "space-between", alignItems: "flex-start", textAlign: "left" }}>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{d.date.slice(8, 10)}</span>
              {d.total_events > 0 && <span style={{ fontSize: 10, opacity: 0.85 }}>{d.total_events} event{d.total_events === 1 ? "" : "s"}</span>}
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
    </div>
  );
}

function WeekView({ anchor, events, kindColor, onSelectDay }: any) {
  const ws = startOfWeek(anchor);
  const days: Date[] = [];
  for (let i = 0; i < 7; i++) { const d = new Date(ws); d.setDate(d.getDate() + i); days.push(d); }
  const byDay: Record<string, any[]> = {};
  for (const e of events) {
    const iso = e.at.slice(0, 10);
    byDay[iso] = byDay[iso] || [];
    byDay[iso].push(e);
  }
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 8 }}>
        {days.map((d) => {
          const iso = isoDate(d);
          const isToday = iso === isoDate(new Date());
          const dayEvents = (byDay[iso] || []).slice(0, 8);
          const more = (byDay[iso] || []).length - dayEvents.length;
          return (
            <div key={iso} style={{ minHeight: 400 }}>
              <button onClick={() => onSelectDay(d)} style={{ width: "100%", background: isToday ? "#5b5cf0" : "#fafbfd", color: isToday ? "#fff" : "#17213a", border: 0, padding: "8px 6px", borderRadius: 8, cursor: "pointer", textAlign: "center", marginBottom: 6 }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em", opacity: 0.85 }}>{DAY_LABELS_SHORT[d.getDay() === 0 ? 6 : d.getDay() - 1]}</div>
                <div style={{ fontSize: 18, fontWeight: 700, marginTop: 2 }}>{d.getDate()}</div>
              </button>
              {dayEvents.map((e: any, i: number) => {
                const tone = kindColor(e.kind);
                return (
                  <a key={i} href={e.link || "#"} style={{ display: "block", background: tone.bg, color: tone.fg, padding: "6px 8px", borderRadius: 6, fontSize: 11, marginBottom: 4, textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={new Date(e.at).toLocaleTimeString() + " · " + e.title}>
                    <span style={{ fontWeight: 700, opacity: 0.75 }}>{new Date(e.at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</span>{" "}
                    {e.title.slice(0, 30)}
                  </a>
                );
              })}
              {more > 0 && <div style={{ fontSize: 10, color: "#8490a4", textAlign: "center", marginTop: 2 }}>+{more} more</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DayView({ anchor, events, kindColor }: any) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24 }}>
      <h2 style={{ margin: "0 0 16px", fontSize: 16, color: "#17213a" }}>{prettyDate(isoDate(anchor))}</h2>
      {events.length === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: "#8490a4" }}>No events on this day.</p>
      ) : (
        <div>
          {events.map((e: any, i: number) => {
            const tone = kindColor(e.kind);
            return (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: 16, padding: "12px 0", borderBottom: i === events.length - 1 ? "0" : "1px solid #f1f4f8" }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#17213a", minWidth: 70 }}>{new Date(e.at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}</span>
                <span style={{ display: "inline-block", padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 700, background: tone.bg, color: tone.fg }}>{e.kind}</span>
                <a href={e.link || "#"} style={{ color: "#17213a", textDecoration: "none", fontSize: 13, flex: 1 }}>{e.title}</a>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function DayDetail({ day }: any) {
  if (!day) return null;
  return (
    <div>
      {day.signups.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600, marginBottom: 6 }}>Signups</div>
          {day.signups.map((s: any) => (
            <div key={s.id} style={{ padding: "8px 0", borderBottom: "1px solid #f1f4f8" }}>
              <a href={"/platform/tenants/" + s.id} style={{ color: "#5b5cf0", textDecoration: "none", fontWeight: 600, fontSize: 13 }}>{s.name}</a>
              <span style={{ color: "#8b95a5", fontSize: 12 }}> · {s.industry}</span>
            </div>
          ))}
        </div>
      )}
      {day.orders > 0 && <p style={{ margin: "6px 0", fontSize: 13, color: "#4b5563" }}>Orders: <b>{day.orders}</b></p>}
      {day.calls > 0 && <p style={{ margin: "6px 0", fontSize: 13, color: "#4b5563" }}>AI calls: <b>{day.calls}</b></p>}
      {day.total_events === 0 && <p style={{ margin: 0, fontSize: 13, color: "#8490a4" }}>No activity on this day.</p>}
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
print(f"Location: {TARGET}")