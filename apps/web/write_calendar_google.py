"""Write the Google-Calendar-style calendar page with full colour system."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "platform" / "calendar" / "page.tsx"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = r'''"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAYS_SHORT = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const HOURS = Array.from({ length: 17 }, (_, i) => i + 6);
const CELL_H = 48;

type View = "month" | "week" | "day";

function isoDate(d: Date) {
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}
function startOfWeek(d: Date) {
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  const out = new Date(d); out.setDate(out.getDate() + diff); out.setHours(0, 0, 0, 0);
  return out;
}
function prettyDate(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

// ============================================================
// COLOUR SYSTEM
// ============================================================

function eventColour(e: any) {
  const kind = e.kind;
  const status = (e.meta?.status || "").toLowerCase();

  if (kind === "signup") return { bg: "#edf2ff", fg: "#566ce1", dot: "#566ce1" };

  if (kind === "call") {
    if (status === "missed") return { bg: "#fff1f1", fg: "#c74646", dot: "#c74646" };
    if (status === "waiting" || status === "ringing") return { bg: "#fff9e6", fg: "#c98c1a", dot: "#e99132" };
    return { bg: "#e9faf2", fg: "#1d9c68", dot: "#1d9c68" };
  }

  if (kind === "order") {
    if (status === "cancelled") return { bg: "#fff1f1", fg: "#c74646", dot: "#c74646" };
    if (status === "preparing" || status === "ready") return { bg: "#fff9e6", fg: "#c98c1a", dot: "#e99132" };
    if (status === "served" || status === "completed") return { bg: "#f2f4f8", fg: "#6b7686", dot: "#8490a4" };
    return { bg: "#e9faf2", fg: "#1d9c68", dot: "#1d9c68" };
  }

  if (kind === "appointment") {
    if (status === "cancelled" || status === "no_show") return { bg: "#fff1f1", fg: "#c74646", dot: "#c74646" };
    if (status === "checked_in" || status === "in_progress" || status === "serving") return { bg: "#fff9e6", fg: "#c98c1a", dot: "#e99132" };
    if (status === "completed") return { bg: "#f2f4f8", fg: "#6b7686", dot: "#8490a4" };
    return { bg: "#e9faf2", fg: "#1d9c68", dot: "#1d9c68" };
  }

  if (kind === "task") {
    if (status === "done" || status === "cancelled") return { bg: "#f2f4f8", fg: "#6b7686", dot: "#8490a4" };
    const p = (e.meta?.priority || "normal").toLowerCase();
    if (p === "urgent") return { bg: "#fff1f1", fg: "#c74646", dot: "#c74646" };
    if (p === "high") return { bg: "#fff0df", fg: "#e99132", dot: "#e99132" };
    if (p === "low") return { bg: "#f2f4f8", fg: "#6b7686", dot: "#6b7686" };
    return { bg: "#edf2ff", fg: "#566ce1", dot: "#566ce1" };
  }

  if (kind === "ticket") {
    if (status === "breached") return { bg: "#fff1f1", fg: "#c74646", dot: "#c74646" };
    if (status === "due_soon") return { bg: "#fff9e6", fg: "#c98c1a", dot: "#e99132" };
    return { bg: "#e9faf2", fg: "#1d9c68", dot: "#1d9c68" };
  }

  return { bg: "#f2f4f8", fg: "#6b7686", dot: "#6b7686" };
}

// ============================================================
// MAIN PAGE
// ============================================================

export default function CalendarPage() {
  const [view, setView] = useState<View>("month");
  const [anchor, setAnchor] = useState<Date>(new Date());
  const [monthData, setMonthData] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [overdue, setOverdue] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const [sidePanelOpen, setSidePanelOpen] = useState(false);

  // Task modal
  const [taskModalOpen, setTaskModalOpen] = useState(false);
  const [taskModalSlot, setTaskModalSlot] = useState<{ date: string; hour: number } | null>(null);
  const [taskForm, setTaskForm] = useState({ title: "", notes: "", priority: "normal", tenant_id: "", kind: "followup" });
  const [taskSaving, setTaskSaving] = useState(false);
  const [taskStatus, setTaskStatus] = useState("");

  // Tenants for picker
  const [tenants, setTenants] = useState<any[]>([]);

  function headers() {
    return {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || ""),
    };
  }

  async function loadMonth() {
    setLoading(true); setError("");
    try {
      const y = anchor.getFullYear(), m = anchor.getMonth() + 1;
      const [c, t] = await Promise.all([
        fetch(api() + "/api/v1/platform/calendar?year=" + y + "&month=" + m, { headers: headers(), cache: "no-store" }).then(r => r.json()),
        fetch(api() + "/api/v1/platform/tasks?status=pending", { headers: headers(), cache: "no-store" }).then(r => r.json()),
      ]);
      if (c?.detail) throw new Error(c.detail);
      if (!c || !Array.isArray(c.days)) throw new Error("Calendar data missing");
      setMonthData(c);
      setTasks(t.items || []);
      setOverdue(t.overdue || 0);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  async function loadRange(startIso: string, endIso: string) {
    setLoading(true); setError("");
    try {
      const [ev, tk] = await Promise.all([
        fetch(api() + "/api/v1/platform/calendar/events?start=" + encodeURIComponent(startIso) + "&end=" + encodeURIComponent(endIso), { headers: headers(), cache: "no-store" }).then(r => r.json()),
        fetch(api() + "/api/v1/platform/tasks?status=pending", { headers: headers(), cache: "no-store" }).then(r => r.json()),
      ]);
      setEvents(ev.items || []);
      setTasks(tk.items || []);
      setOverdue(tk.overdue || 0);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  async function loadTenants() {
    try {
      const r = await fetch(api() + "/api/v1/platform/tenants", { headers: headers(), cache: "no-store" });
      const x = await r.json();
      setTenants(x.items || []);
    } catch {}
  }

  useEffect(() => {
    if (view === "month") void loadMonth();
    else if (view === "week") {
      const ws = startOfWeek(anchor); const we = new Date(ws); we.setDate(we.getDate() + 7);
      void loadRange(ws.toISOString(), we.toISOString());
    } else {
      const ds = new Date(anchor); ds.setHours(0, 0, 0, 0);
      const de = new Date(anchor); de.setHours(23, 59, 59, 999);
      void loadRange(ds.toISOString(), de.toISOString());
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, anchor.getTime()]);

  useEffect(() => { void loadTenants(); }, []);

  function prev() {
    const n = new Date(anchor);
    if (view === "month") n.setMonth(n.getMonth() - 1);
    else if (view === "week") n.setDate(n.getDate() - 7);
    else n.setDate(n.getDate() - 1);
    setAnchor(n); setSelectedDay(null); setSidePanelOpen(false);
  }
  function next() {
    const n = new Date(anchor);
    if (view === "month") n.setMonth(n.getMonth() + 1);
    else if (view === "week") n.setDate(n.getDate() + 7);
    else n.setDate(n.getDate() + 1);
    setAnchor(n); setSelectedDay(null); setSidePanelOpen(false);
  }
  function goToday() { setAnchor(new Date()); setSelectedDay(null); setSidePanelOpen(false); }
  function jumpToDate(iso: string) {
    if (!iso) return;
    const d = new Date(iso + "T00:00:00");
    if (isNaN(d.getTime())) return;
    setAnchor(d); setSelectedDay(null); setSidePanelOpen(false);
  }

  function openTaskModal(dateIso: string, hour: number) {
    setTaskModalSlot({ date: dateIso, hour });
    setTaskForm({ title: "", notes: "", priority: "normal", tenant_id: "", kind: "followup" });
    setTaskStatus("");
    setTaskModalOpen(true);
  }

  async function createTask() {
    if (!taskModalSlot || !taskForm.title.trim()) { setTaskStatus("Title is required"); return; }
    setTaskSaving(true); setTaskStatus("");
    const due = taskModalSlot.date + "T" + String(taskModalSlot.hour).padStart(2, "0") + ":00:00";
    try {
      const r = await fetch(api() + "/api/v1/platform/tasks", {
        method: "POST", headers: headers(),
        body: JSON.stringify({ title: taskForm.title, notes: taskForm.notes, due_at: due, priority: taskForm.priority, tenant_id: taskForm.tenant_id || null, kind: taskForm.kind }),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Create failed");
      setTaskStatus("Task created");
      setTimeout(() => { setTaskModalOpen(false); void loadMonth(); }, 700);
    } catch (e: any) { setTaskStatus(e.message); }
    setTaskSaving(false);
  }

  async function completeTask(taskId: string) {
    try {
      await fetch(api() + "/api/v1/platform/tasks/" + taskId + "/status", {
        method: "PATCH", headers: headers(), body: JSON.stringify({ status: "done" }),
      });
      setTasks((prev) => prev.filter((t) => t.id !== taskId));
    } catch {}
  }

  const rangeLabel = (() => {
    if (view === "month") return MONTHS[anchor.getMonth()] + " " + anchor.getFullYear();
    if (view === "week") {
      const ws = startOfWeek(anchor); const we = new Date(ws); we.setDate(we.getDate() + 6);
      return ws.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + " – " + we.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    }
    return prettyDate(isoDate(anchor));
  })();

  return (
    <div>
      <div style={{ marginBottom: 20, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Calendar</h1>
          <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
            Signups, calls, orders, tasks — Google-style month, week, and day views.
            {overdue > 0 && <span style={{ marginLeft: 10, padding: "2px 8px", borderRadius: 20, background: "#fff1f1", color: "#c74646", fontWeight: 700, fontSize: 11 }}>{overdue} overdue</span>}
          </p>
        </div>
      </div>

      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      {/* Top bar */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
        <button onClick={prev} style={navBtn}>‹</button>
        <button onClick={next} style={navBtn}>›</button>
        <button onClick={goToday} style={{ ...navBtn, width: "auto", padding: "0 14px", fontWeight: 700 }}>Today</button>
        <span style={{ fontSize: 16, fontWeight: 700, color: "#17213a", minWidth: 200 }}>{rangeLabel}</span>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#75839a" }}>
          <span style={{ fontWeight: 600 }}>Jump to</span>
          <input type="date" value={isoDate(anchor)} onChange={(e) => jumpToDate(e.target.value)} style={dateInput} />
        </label>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4, background: "#f2f4f8", padding: 4, borderRadius: 10 }}>
          {(["month", "week", "day"] as View[]).map((v) => (
            <button key={v} onClick={() => setView(v)} style={{ border: 0, padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: "pointer", background: view === v ? "#fff" : "transparent", color: view === v ? "#17213a" : "#75839a", boxShadow: view === v ? "0 2px 6px rgba(17,24,39,0.06)" : "none", textTransform: "capitalize" }}>{v}</button>
          ))}
        </div>
      </div>

      {/* Main content */}
      <div style={{ display: "flex", gap: 16 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {loading ? (
            <div style={loadingBox}>Loading…</div>
          ) : view === "month" ? (
            <MonthGrid data={monthData} onSelect={(iso: string) => { setSelectedDay(iso); setSidePanelOpen(true); }} selected={selectedDay} />
          ) : view === "week" ? (
            <WeekGrid anchor={anchor} events={events} onCreateTask={openTaskModal} onSelectDay={(d: Date) => { setAnchor(d); setView("day"); }} />
          ) : (
            <DayGrid anchor={anchor} events={events} onCreateTask={openTaskModal} />
          )}

          {/* Legend */}
          <Legend />

          {/* Pending tasks quick list */}
          {tasks.length > 0 && (
            <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20, marginTop: 18 }}>
              <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "#17213a" }}>Pending tasks ({tasks.length})</h3>
              <div>
                {tasks.slice(0, 10).map((t) => {
                  const c = eventColour({ kind: "task", meta: { priority: t.priority, status: t.status } });
                  return (
                    <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid #f1f4f8" }}>
                      <input type="checkbox" onChange={() => completeTask(t.id)} style={{ width: "auto", margin: 0, cursor: "pointer" }} />
                      <span style={{ width: 8, height: 8, borderRadius: 4, background: c.dot, flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 13, color: "#17213a", fontWeight: 600 }}>{t.title}</div>
                        <div style={{ fontSize: 11, color: "#8b95a5" }}>
                          {new Date(t.due_at).toLocaleString()} · {t.priority}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Side panel for selected day (month view) */}
        {sidePanelOpen && selectedDay && (
          <SidePanel dayIso={selectedDay} monthData={monthData} onClose={() => { setSidePanelOpen(false); setSelectedDay(null); }} />
        )}
      </div>

      {/* Create task modal */}
      {taskModalOpen && taskModalSlot && (
        <div style={modalBackdrop}>
          <div style={modalBox}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 16, color: "#17213a" }}>New task</h2>
              <button onClick={() => setTaskModalOpen(false)} style={{ background: "transparent", border: 0, color: "#8490a4", fontSize: 20, cursor: "pointer" }}>×</button>
            </div>
            <p style={{ margin: "0 0 16px", fontSize: 12, color: "#75839a" }}>
              {taskModalSlot.date} · {String(taskModalSlot.hour).padStart(2, "0")}:00
            </p>

            <label style={labelStyle}>Title
              <input value={taskForm.title} onChange={(e) => setTaskForm({ ...taskForm, title: e.target.value })} placeholder="e.g. Call Test Biz about loyalty setup" style={inputStyle} autoFocus />
            </label>

            <label style={labelStyle}>Notes
              <textarea value={taskForm.notes} onChange={(e) => setTaskForm({ ...taskForm, notes: e.target.value })} rows={4} placeholder="Details, context, follow-up questions…" style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }} />
            </label>

            <label style={labelStyle}>Priority
              <select value={taskForm.priority} onChange={(e) => setTaskForm({ ...taskForm, priority: e.target.value })} style={inputStyle}>
                <option value="low">Low (grey)</option>
                <option value="normal">Normal (blue)</option>
                <option value="high">High (orange)</option>
                <option value="urgent">Urgent (red)</option>
              </select>
            </label>

            <label style={labelStyle}>Related tenant (optional)
              <select value={taskForm.tenant_id} onChange={(e) => setTaskForm({ ...taskForm, tenant_id: e.target.value })} style={inputStyle}>
                <option value="">— None —</option>
                {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </label>

            {taskStatus && <p style={{ margin: "8px 0", fontSize: 12, color: "#1aa76c" }}>{taskStatus}</p>}

            <div style={{ display: "flex", gap: 10, marginTop: 16, justifyContent: "flex-end" }}>
              <button onClick={() => setTaskModalOpen(false)} style={ghostBtn}>Cancel</button>
              <button onClick={createTask} disabled={taskSaving} style={primaryBtn}>
                {taskSaving ? "Saving…" : "Create task"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// MONTH GRID
// ============================================================

function MonthGrid({ data, onSelect, selected }: any) {
  if (!data) return null;
  const eventsByDay: Record<string, any[]> = {};
  for (const d of data.days) {
    if (d.signups?.length) eventsByDay[d.date] = d.signups.map((s: any) => ({ kind: "signup", title: s.name, meta: {} }));
  }
  const today = isoDate(new Date());

  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 0, marginBottom: 4 }}>
        {DAYS_SHORT.map((d) => (
          <div key={d} style={{ textAlign: "center", fontSize: 10, color: "#8b97a9", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", padding: 6 }}>{d}</div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 0 }}>
        {Array.from({ length: data.first_day_weekday - 1 }).map((_, i) => (
          <div key={"pad" + i} style={{ borderTop: "1px solid #f1f4f8", borderLeft: i === 0 ? "1px solid #f1f4f8" : "none", minHeight: 100, background: "#fafbfd" }} />
        ))}
        {data.days.map((d: any) => {
          const isToday = d.date === today;
          const isSelected = selected === d.date;
          const chips = eventsByDay[d.date] || [];
          const visible = chips.slice(0, 3);
          const more = chips.length - visible.length;

          return (
            <button
              key={d.date}
              onClick={() => onSelect(d.date)}
              style={{
                minHeight: 100, padding: 6, textAlign: "left",
                background: isSelected ? "#f5f4ff" : "#fff",
                border: "1px solid #f1f4f8",
                borderLeft: "1px solid #f1f4f8",
                borderTop: "1px solid #f1f4f8",
                cursor: "pointer", display: "flex", flexDirection: "column", gap: 3,
                position: "relative",
              }}
            >
              <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 4 }}>
                {d.total_events > 0 && <span style={{ fontSize: 9, color: "#8b95a9" }}>{d.total_events}</span>}
                <span style={{
                  fontSize: 12, fontWeight: 700,
                  color: isToday ? "#fff" : "#17213a",
                  background: isToday ? "#5b5cf0" : "transparent",
                  width: 22, height: 22, borderRadius: 11,
                  display: "grid", placeItems: "center",
                }}>{d.date.slice(8, 10)}</span>
              </div>
              {visible.map((e: any, i: number) => {
                const c = eventColour(e);
                return (
                  <div key={i} style={{ background: c.bg, color: c.fg, padding: "2px 5px", borderRadius: 4, fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 600 }}>
                    {e.title}
                  </div>
                );
              })}
              {more > 0 && <div style={{ fontSize: 9, color: "#8490a4", paddingLeft: 4 }}>+{more} more</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// WEEK GRID (with hour rows and clickable empty slots)
// ============================================================

function WeekGrid({ anchor, events, onCreateTask, onSelectDay }: any) {
  const ws = startOfWeek(anchor);
  const days: Date[] = [];
  for (let i = 0; i < 7; i++) { const d = new Date(ws); d.setDate(d.getDate() + i); days.push(d); }

  const byDayHour: Record<string, Record<number, any[]>> = {};
  for (const e of events) {
    const d = new Date(e.at);
    const iso = isoDate(d);
    const h = d.getHours();
    byDayHour[iso] = byDayHour[iso] || {};
    byDayHour[iso][h] = byDayHour[iso][h] || [];
    byDayHour[iso][h].push(e);
  }

  const now = new Date();
  const nowIso = isoDate(now);
  const nowHour = now.getHours();
  const nowMinute = now.getMinutes();

  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 16, overflowX: "auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "60px repeat(7, minmax(120px, 1fr))", minWidth: 900 }}>
        {/* Header row */}
        <div />
        {days.map((d) => {
          const iso = isoDate(d);
          const isToday = iso === nowIso;
          return (
            <button key={iso} onClick={() => onSelectDay(d)} style={{ background: "transparent", color: "#17213a", border: 0, padding: "8px 6px", cursor: "pointer", textAlign: "center", borderRadius: 8 }}>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700, color: "#8b97a9" }}>{DAYS_SHORT[d.getDay() === 0 ? 6 : d.getDay() - 1]}</div>
              <div style={{ fontSize: 20, fontWeight: 700, marginTop: 2, color: isToday ? "#5b5cf0" : "#17213a" }}>{d.getDate()}</div>
            </button>
          );
        })}

        {/* Hour rows */}
        {HOURS.map((h) => (
          <div key={"row" + h} style={{ display: "contents" }}>
            <div style={{ fontSize: 11, color: "#8b97a9", textAlign: "right", paddingRight: 10, paddingTop: 4, height: CELL_H, borderTop: "1px solid #f1f4f8" }}>
              {String(h).padStart(2, "0")}:00
            </div>
            {days.map((d) => {
              const iso = isoDate(d);
              const cellEvents = byDayHour[iso]?.[h] || [];
              const isNowCell = iso === nowIso && h === nowHour;
              return (
                <div
                  key={iso + "-" + h}
                  onClick={() => onCreateTask(iso, h)}
                  style={{
                    height: CELL_H, borderTop: "1px solid #f1f4f8", borderLeft: "1px solid #f1f4f8",
                    padding: 3, position: "relative", cursor: "pointer",
                    background: isNowCell ? "#f9f8ff" : "transparent",
                  }}
                  title="Click to add a task"
                >
                  {cellEvents.map((e: any, i: number) => {
                    const c = eventColour(e);
                    return (
                      <a
                        key={i}
                        href={e.link || "#"}
                        onClick={(ev) => ev.stopPropagation()}
                        title={new Date(e.at).toLocaleTimeString() + " · " + e.title}
                        style={{
                          display: "block",
                          background: c.bg, color: c.fg,
                          padding: "3px 6px", borderRadius: 5, fontSize: 10,
                          marginBottom: 2, textDecoration: "none",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                          borderLeft: "3px solid " + c.dot,
                          fontWeight: 600,
                        }}
                      >
                        {e.title.slice(0, 28)}
                      </a>
                    );
                  })}
                  {/* Red current-time line */}
                  {isNowCell && (
                    <div style={{
                      position: "absolute", left: 0, right: 0,
                      top: (nowMinute / 60) * CELL_H,
                      height: 2, background: "#c74646", zIndex: 10,
                      pointerEvents: "none",
                    }}>
                      <span style={{ position: "absolute", left: -6, top: -4, width: 10, height: 10, borderRadius: 5, background: "#c74646" }} />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

// ============================================================
// DAY GRID
// ============================================================

function DayGrid({ anchor, events, onCreateTask }: any) {
  const iso = isoDate(anchor);
  const byHour: Record<number, any[]> = {};
  for (const e of events) {
    const h = new Date(e.at).getHours();
    byHour[h] = byHour[h] || [];
    byHour[h].push(e);
  }
  const now = new Date();
  const isToday = iso === isoDate(now);
  const nowHour = now.getHours();
  const nowMinute = now.getMinutes();

  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24 }}>
      <h2 style={{ margin: "0 0 16px", fontSize: 16, color: "#17213a" }}>{prettyDate(iso)}</h2>
      <div>
        {HOURS.map((h) => {
          const rowEvents = byHour[h] || [];
          const isNowCell = isToday && h === nowHour;
          return (
            <div
              key={h}
              onClick={() => onCreateTask(iso, h)}
              style={{
                display: "flex", gap: 16, minHeight: 52,
                borderTop: "1px solid #f1f4f8",
                paddingTop: 6, paddingBottom: 6,
                cursor: "pointer", position: "relative",
                background: isNowCell ? "#f9f8ff" : "transparent",
              }}
              title="Click to add a task"
            >
              <span style={{ fontSize: 12, fontWeight: 700, color: "#8b97a9", width: 60, textAlign: "right", paddingTop: 4 }}>
                {String(h).padStart(2, "0")}:00
              </span>
              <div style={{ flex: 1, position: "relative" }}>
                {rowEvents.length === 0 ? (
                  <span style={{ color: "#c1c8d1", fontSize: 12 }}>—</span>
                ) : (
                  rowEvents.map((e: any, i: number) => {
                    const c = eventColour(e);
                    return (
                      <a
                        key={i}
                        href={e.link || "#"}
                        onClick={(ev) => ev.stopPropagation()}
                        style={{
                          display: "inline-block",
                          background: c.bg, color: c.fg,
                          padding: "4px 10px", borderRadius: 6, fontSize: 12,
                          marginRight: 6, marginBottom: 4, textDecoration: "none",
                          borderLeft: "3px solid " + c.dot,
                          fontWeight: 600,
                        }}
                      >
                        {new Date(e.at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })} · {e.title}
                      </a>
                    );
                  })
                )}
                {isNowCell && (
                  <div style={{
                    position: "absolute", left: 0, right: 0,
                    top: (nowMinute / 60) * 52,
                    height: 2, background: "#c74646", zIndex: 10, pointerEvents: "none",
                  }}>
                    <span style={{ position: "absolute", left: -6, top: -4, width: 10, height: 10, borderRadius: 5, background: "#c74646" }} />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// SIDE PANEL (month view)
// ============================================================

function SidePanel({ dayIso, monthData, onClose }: any) {
  const day = monthData?.days.find((d: any) => d.date === dayIso);
  return (
    <div style={{ width: 340, flexShrink: 0, background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700 }}>
            {new Date(dayIso + "T00:00:00").toLocaleDateString(undefined, { weekday: "long" })}
          </div>
          <div style={{ fontSize: 22, fontWeight: 700, color: "#17213a" }}>
            {new Date(dayIso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "long" })}
          </div>
        </div>
        <button onClick={onClose} style={{ background: "transparent", border: 0, color: "#8490a4", fontSize: 20, cursor: "pointer" }}>×</button>
      </div>

      {!day || day.total_events === 0 ? (
        <p style={{ margin: 0, fontSize: 13, color: "#8490a4" }}>Nothing scheduled on this day.</p>
      ) : (
        <div>
          {day.signups?.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 10, color: "#8b95a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 6 }}>Signups</div>
              {day.signups.map((s: any) => (
                <a key={s.id} href={"/platform/tenants/" + s.id} style={{ display: "block", padding: "8px 10px", borderRadius: 8, background: "#edf2ff", color: "#566ce1", textDecoration: "none", fontSize: 12, marginBottom: 4, fontWeight: 600 }}>
                  {s.name}
                </a>
              ))}
            </div>
          )}
          {day.orders > 0 && (
            <div style={{ marginBottom: 10 }}>
              <span style={{ fontSize: 10, color: "#8b95a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700 }}>Orders: </span>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#17213a" }}>{day.orders}</span>
            </div>
          )}
          {day.calls > 0 && (
            <div>
              <span style={{ fontSize: 10, color: "#8b95a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700 }}>AI calls: </span>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#17213a" }}>{day.calls}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// LEGEND
// ============================================================

function Legend() {
  const items = [
    { label: "Confirmed", colour: "#1d9c68" },
    { label: "In progress", colour: "#e99132" },
    { label: "Cancelled / missed", colour: "#c74646" },
    { label: "Completed (past)", colour: "#8490a4" },
    { label: "Signup", colour: "#566ce1" },
  ];
  return (
    <div style={{ marginTop: 14, padding: "10px 14px", background: "#fafbfd", border: "1px solid #f1f4f8", borderRadius: 10, display: "flex", gap: 16, flexWrap: "wrap", fontSize: 11, color: "#75839a", alignItems: "center" }}>
      <span style={{ fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", fontSize: 10 }}>Legend</span>
      {items.map((x) => (
        <span key={x.label} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <span style={{ width: 10, height: 10, borderRadius: 5, background: x.colour, display: "inline-block" }} />
          {x.label}
        </span>
      ))}
    </div>
  );
}

// ============================================================
// STYLES
// ============================================================

const navBtn: React.CSSProperties = { background: "#fff", border: "1px solid #d7dce5", width: 38, height: 38, borderRadius: 10, fontSize: 18, cursor: "pointer", color: "#17213a" };
const dateInput: React.CSSProperties = { padding: "8px 10px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, background: "#fff", outline: "none" };
const loadingBox: React.CSSProperties = { padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14 };
const labelStyle: React.CSSProperties = { display: "block", fontSize: 12, fontWeight: 600, color: "#17213a", marginBottom: 12 };
const inputStyle: React.CSSProperties = { display: "block", width: "100%", marginTop: 6, padding: 10, borderRadius: 8, border: "1px solid #d7dce5", fontSize: 13, outline: "none" };
const primaryBtn: React.CSSProperties = { background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: "pointer" };
const ghostBtn: React.CSSProperties = { background: "#fff", color: "#17213a", border: "1px solid #e5e7eb", padding: "11px 22px", borderRadius: 10, fontWeight: 600, fontSize: 13, cursor: "pointer" };
const modalBackdrop: React.CSSProperties = { position: "fixed", inset: 0, background: "rgba(7,21,46,0.5)", backdropFilter: "blur(4px)", zIndex: 100, display: "grid", placeItems: "center", padding: 20 };
const modalBox: React.CSSProperties = { width: "min(520px, 100%)", background: "#fff", borderRadius: 16, padding: 24, boxShadow: "0 25px 70px rgba(7,21,46,0.25)" };
'''

TARGET.write_text(CONTENT, encoding="utf-8")
print(f"File saved: {TARGET.stat().st_size} bytes")
print(f"Location: {TARGET}")