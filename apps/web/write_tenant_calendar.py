"""Write the tenant calendar page — same features as admin, tenant-scoped."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "dashboard" / "calendar" / "page.tsx"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = r'''"use client";
import { useEffect, useRef, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"];
const DAYS_SHORT = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const HOURS = Array.from({ length: 17 }, (_, i) => i + 6);
const CELL_H = 42;
const MIN_SNAP = 15;

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
function addMinutes(d: Date, m: number) { const x = new Date(d); x.setMinutes(x.getMinutes() + m); return x; }
function fmtTime(d: Date) { return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" }); }
function fmtHM(h: number, m: number) {
  const ampm = h >= 12 ? "PM" : "AM";
  const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return h12 + ":" + String(m).padStart(2, "0") + " " + ampm;
}

function eventColour(e: any) {
  const kind = e.kind;
  const status = (e.meta?.status || "").toLowerCase();
  if (kind === "signup") return { bg: "#edf2ff", fg: "#3448b8", border: "#566ce1" };
  if (kind === "call") {
    if (status === "missed") return { bg: "#fff1f1", fg: "#9c2f2f", border: "#c74646" };
    if (status === "waiting" || status === "ringing") return { bg: "#fff9e6", fg: "#9a6b10", border: "#e99132" };
    return { bg: "#e9faf2", fg: "#166b47", border: "#1d9c68" };
  }
  if (kind === "order") {
    if (status === "cancelled") return { bg: "#fff1f1", fg: "#9c2f2f", border: "#c74646" };
    if (status === "preparing" || status === "ready") return { bg: "#fff9e6", fg: "#9a6b10", border: "#e99132" };
    if (status === "served" || status === "completed") return { bg: "#f2f4f8", fg: "#5a6473", border: "#8490a4" };
    return { bg: "#e9faf2", fg: "#166b47", border: "#1d9c68" };
  }
  if (kind === "appointment") {
    if (status === "cancelled" || status === "no_show") return { bg: "#fff1f1", fg: "#9c2f2f", border: "#c74646" };
    if (status === "checked_in" || status === "in_progress" || status === "serving") return { bg: "#fff9e6", fg: "#9a6b10", border: "#e99132" };
    if (status === "completed") return { bg: "#f2f4f8", fg: "#5a6473", border: "#8490a4" };
    return { bg: "#e9faf2", fg: "#166b47", border: "#1d9c68" };
  }
  if (kind === "task") {
    if (status === "done" || status === "cancelled") return { bg: "#f2f4f8", fg: "#5a6473", border: "#8490a4" };
    const p = (e.meta?.priority || "normal").toLowerCase();
    if (p === "urgent") return { bg: "#fff1f1", fg: "#9c2f2f", border: "#c74646" };
    if (p === "high") return { bg: "#fff0df", fg: "#9a4d10", border: "#e99132" };
    if (p === "low") return { bg: "#f2f4f8", fg: "#5a6473", border: "#8490a4" };
    return { bg: "#edf2ff", fg: "#3448b8", border: "#566ce1" };
  }
  return { bg: "#f2f4f8", fg: "#5a6473", border: "#8490a4" };
}

export default function TenantCalendarPage() {
  const [tenantId, setTenantId] = useState("");
  const [view, setView] = useState<View>("month");
  const [anchor, setAnchor] = useState<Date>(new Date());
  const [monthData, setMonthData] = useState<any>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [modalTask, setModalTask] = useState<any>(null);
  const [modalStatus, setModalStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [sidePanel, setSidePanel] = useState<string | null>(null);

  function headers() {
    return { "Content-Type": "application/json", Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || "") };
  }

  useEffect(() => {
    const raw = localStorage.getItem("ago_tenant");
    let t: any = null;
    try { t = raw ? JSON.parse(raw) : null; } catch {}
    if (!t?.id) { window.location.href = "/dashboard"; return; }
    setTenantId(t.id);
  }, []);

  async function loadMonth() {
    if (!tenantId) return;
    setLoading(true); setError("");
    try {
      const y = anchor.getFullYear(), m = anchor.getMonth() + 1;
      const [c, tk] = await Promise.all([
        fetch(api() + "/api/v1/tenants/" + tenantId + "/calendar?year=" + y + "&month=" + m, { headers: headers(), cache: "no-store" }).then(r => r.json()),
        fetch(api() + "/api/v1/tenants/" + tenantId + "/calendar/tasks?status=pending", { headers: headers(), cache: "no-store" }).then(r => r.json()),
      ]);
      if (c?.detail) throw new Error(c.detail);
      if (!c || !Array.isArray(c.days)) throw new Error("Calendar data missing");
      setMonthData(c);
      setTasks(tk.items || []);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  async function loadRange(startIso: string, endIso: string) {
    if (!tenantId) return;
    setLoading(true); setError("");
    try {
      const [ev, tk] = await Promise.all([
        fetch(api() + "/api/v1/tenants/" + tenantId + "/calendar/events?start=" + encodeURIComponent(startIso) + "&end=" + encodeURIComponent(endIso), { headers: headers(), cache: "no-store" }).then(r => r.json()),
        fetch(api() + "/api/v1/tenants/" + tenantId + "/calendar/tasks?status=pending", { headers: headers(), cache: "no-store" }).then(r => r.json()),
      ]);
      setEvents(ev.items || []);
      setTasks(tk.items || []);
    } catch (e: any) { setError(e.message); }
    setLoading(false);
  }

  useEffect(() => {
    if (!tenantId) return;
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
  }, [view, anchor.getTime(), tenantId]);

  function openCreate(start: Date, end?: Date) {
    const e = end || addMinutes(start, 30);
    setModalTask({
      title: "",
      notes: "",
      start: start.toISOString(),
      end: e.toISOString(),
      priority: "normal",
      kind: "task",
      all_day: false,
    });
    setModalStatus("");
    setModalOpen(true);
  }

  function openEdit(task: any) {
    setModalTask({
      id: task.id || task.meta?.task_id,
      title: task.title,
      notes: task.notes || "",
      start: task.due_at || task.at,
      end: task.due_at_plus || (task.ends_at ? task.ends_at : addMinutes(new Date(task.at || task.due_at), task.duration_minutes || 30).toISOString()),
      priority: task.priority || (task.meta?.priority || "normal"),
      kind: "task",
      all_day: !!task.all_day,
    });
    setModalStatus("");
    setModalOpen(true);
  }

  async function saveTask() {
    if (!modalTask || !tenantId) return;
    if (!modalTask.title.trim()) { setModalStatus("Title is required"); return; }
    setSaving(true); setModalStatus("");
    try {
      const start = new Date(modalTask.start);
      const end = new Date(modalTask.end);
      const duration_minutes = Math.max(5, Math.round((end.getTime() - start.getTime()) / 60000));
      const r = await fetch(api() + "/api/v1/tenants/" + tenantId + "/calendar/tasks", {
        method: "POST", headers: headers(),
        body: JSON.stringify({
          title: modalTask.title,
          notes: modalTask.notes,
          due_at: modalTask.start,
          priority: modalTask.priority,
          kind: modalTask.kind || "followup",
          duration_minutes,
          all_day: !!modalTask.all_day,
        }),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Save failed");
      setModalStatus("Saved");
      setTimeout(() => {
        setModalOpen(false);
        void loadMonth();
        if (view !== "month") {
          const ws = startOfWeek(anchor); const we = new Date(ws); we.setDate(we.getDate() + 7);
          void loadRange(ws.toISOString(), we.toISOString());
        }
      }, 600);
    } catch (e: any) { setModalStatus(e.message); }
    setSaving(false);
  }

  async function deleteTask(id: string) {
    if (!tenantId) return;
    if (!confirm("Delete this task?")) return;
    try {
      await fetch(api() + "/api/v1/tenants/" + tenantId + "/calendar/tasks/" + id, { method: "DELETE", headers: headers() });
      setModalOpen(false);
      void loadMonth();
    } catch {}
  }

  async function completeTask(id: string) {
    if (!tenantId) return;
    try {
      await fetch(api() + "/api/v1/tenants/" + tenantId + "/calendar/tasks/" + id + "/status", { method: "PATCH", headers: headers(), body: JSON.stringify({ status: "done" }) });
      setTasks((p) => p.filter((t) => t.id !== id));
    } catch {}
  }

  const rangeLabel = (() => {
    if (view === "month") return MONTHS[anchor.getMonth()] + " " + anchor.getFullYear();
    if (view === "week") {
      const ws = startOfWeek(anchor); const we = new Date(ws); we.setDate(we.getDate() + 6);
      return ws.toLocaleDateString(undefined, { day: "numeric", month: "short" }) + " – " + we.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    }
    return anchor.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  })();

  if (!tenantId) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Calendar</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Your bookings, orders, calls, and tasks. Click anywhere to add a task.
        </p>
      </div>

      {error && <p style={{ color: "#b00", fontSize: 13, marginBottom: 12 }}>{error}</p>}

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 16, flexWrap: "wrap" }}>
        <button onClick={() => { const n = new Date(anchor); if (view==="month") n.setMonth(n.getMonth()-1); else if (view==="week") n.setDate(n.getDate()-7); else n.setDate(n.getDate()-1); setAnchor(n); }} style={navBtn}>‹</button>
        <button onClick={() => { const n = new Date(anchor); if (view==="month") n.setMonth(n.getMonth()+1); else if (view==="week") n.setDate(n.getDate()+7); else n.setDate(n.getDate()+1); setAnchor(n); }} style={navBtn}>›</button>
        <button onClick={() => setAnchor(new Date())} style={{ ...navBtn, width: "auto", padding: "0 14px", fontWeight: 700 }}>Today</button>
        <span style={{ fontSize: 16, fontWeight: 700, color: "#17213a", minWidth: 220 }}>{rangeLabel}</span>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "#75839a" }}>
          <span style={{ fontWeight: 600 }}>Jump to</span>
          <input type="date" value={isoDate(anchor)} onChange={(e) => { const d = new Date(e.target.value + "T00:00:00"); if (!isNaN(d.getTime())) setAnchor(d); }} style={dateInput} />
        </label>
        <div style={{ marginLeft: "auto", display: "flex", gap: 4, background: "#f2f4f8", padding: 4, borderRadius: 10 }}>
          {(["month", "week", "day"] as View[]).map((v) => (
            <button key={v} onClick={() => setView(v)} style={{ border: 0, padding: "8px 16px", borderRadius: 8, fontSize: 12, fontWeight: 700, cursor: "pointer", background: view === v ? "#fff" : "transparent", color: view === v ? "#17213a" : "#75839a", boxShadow: view === v ? "0 2px 6px rgba(17,24,39,0.06)" : "none", textTransform: "capitalize" }}>{v}</button>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {loading ? (
            <div style={loadingBox}>Loading…</div>
          ) : view === "month" ? (
            <MonthView data={monthData} onCreate={openCreate} onEdit={openEdit} onSelectDay={setSidePanel} />
          ) : view === "week" ? (
            <TimeGridView anchor={anchor} events={events} days={7} onCreate={openCreate} onEdit={openEdit} onDayHeader={(d) => { setAnchor(d); setView("day"); }} />
          ) : (
            <TimeGridView anchor={anchor} events={events} days={1} onCreate={openCreate} onEdit={openEdit} onDayHeader={null} />
          )}
        </div>
        {sidePanel && view === "month" && (
          <SidePanel dayIso={sidePanel} monthData={monthData} tasks={tasks} onClose={() => setSidePanel(null)} onCreate={openCreate} />
        )}
      </div>

      <Legend />

      {tasks.length > 0 && (
        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20, marginTop: 18 }}>
          <h3 style={{ margin: "0 0 12px", fontSize: 14, color: "#17213a" }}>Pending tasks ({tasks.length})</h3>
          {tasks.slice(0, 10).map((t) => {
            const c = eventColour({ kind: "task", meta: { priority: t.priority, status: t.status } });
            return (
              <div key={t.id} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 0", borderBottom: "1px solid #f1f4f8" }}>
                <input type="checkbox" onChange={() => completeTask(t.id)} style={{ width: "auto", margin: 0, cursor: "pointer" }} />
                <span style={{ width: 10, height: 10, borderRadius: 5, background: c.border, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, color: "#17213a", fontWeight: 600 }}>{t.title}</div>
                  <div style={{ fontSize: 11, color: "#8b95a5" }}>
                    {new Date(t.due_at).toLocaleString()} · {t.duration_minutes || 30} min · {t.priority}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {modalOpen && modalTask && (
        <TaskModal
          task={modalTask}
          status={modalStatus}
          saving={saving}
          onChange={setModalTask}
          onSave={saveTask}
          onDelete={modalTask.id ? () => deleteTask(modalTask.id) : undefined}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  );
}

function MonthView({ data, onCreate, onEdit, onSelectDay }: any) {
  if (!data) return null;
  const today = isoDate(new Date());
  const eventsByDay: Record<string, any[]> = {};
  for (const d of data.days) {
    if (d.signups?.length) {
      eventsByDay[d.date] = d.signups.map((s: any) => ({ kind: "signup", title: s.name, meta: {} }));
    }
  }
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 16 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", marginBottom: 4 }}>
        {DAYS_SHORT.map((d) => (
          <div key={d} style={{ textAlign: "center", fontSize: 10, color: "#8b97a9", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", padding: 8 }}>{d}</div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 0 }}>
        {Array.from({ length: data.first_day_weekday - 1 }).map((_, i) => (
          <div key={"pad" + i} style={{ borderTop: "1px solid #f1f4f8", borderLeft: "1px solid #f1f4f8", minHeight: 88, background: "#fafbfd" }} />
        ))}
        {data.days.map((d: any) => {
          const isToday = d.date === today;
          const chips = eventsByDay[d.date] || [];
          return (
            <div key={d.date} onClick={() => onSelectDay && onSelectDay(d.date)} style={{ minHeight: 88, padding: 4, cursor: "pointer", borderTop: "1px solid #f1f4f8", borderLeft: "1px solid #f1f4f8", background: "#fff", display: "flex", flexDirection: "column", gap: 2, overflow: "hidden" }}>
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <span style={{ width: 22, height: 22, borderRadius: 11, display: "grid", placeItems: "center", background: isToday ? "#5b5cf0" : "transparent", color: isToday ? "#fff" : "#17213a", fontSize: 12, fontWeight: 700 }}>{d.date.slice(8, 10)}</span>
              </div>
              {chips.slice(0, 2).map((e: any, i: number) => {
                const c = eventColour(e);
                return (
                  <div key={i} style={{ background: c.bg, color: c.fg, borderLeft: "3px solid " + c.border, padding: "2px 5px", borderRadius: 4, fontSize: 10, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 600 }}>
                    {e.title}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TimeGridView({ anchor, events, days, onCreate, onEdit, onDayHeader }: any) {
  const ws = days === 7 ? startOfWeek(anchor) : anchor;
  const dayList: Date[] = [];
  for (let i = 0; i < days; i++) {
    const d = new Date(ws); d.setDate(d.getDate() + i); d.setHours(0, 0, 0, 0);
    dayList.push(d);
  }
  const now = new Date();
  const nowIso = isoDate(now);
  const nowMinutes = now.getHours() * 60 + now.getMinutes();

  const dragRef = useRef<any>({ active: false, dayIso: null, startMinutes: 0, currentMinutes: 0 });
  const [dragVersion, setDragVersion] = useState(0);

  const eventsByDay: Record<string, any[]> = {};
  for (const e of events) {
    const iso = isoDate(new Date(e.at));
    eventsByDay[iso] = eventsByDay[iso] || [];
    eventsByDay[iso].push(e);
  }

  const gridStart = HOURS[0] * 60;
  const gridEnd = (HOURS[HOURS.length - 1] + 1) * 60;
  const gridHeight = ((gridEnd - gridStart) / 60) * CELL_H;

  function yToMinutes(y: number) {
    const raw = gridStart + (y / CELL_H) * 60;
    const snapped = Math.round(raw / MIN_SNAP) * MIN_SNAP;
    return Math.max(gridStart, Math.min(gridEnd - MIN_SNAP, snapped));
  }

  function onMouseDownCell(e: React.MouseEvent, dayIso: string) {
    if ((e.target as HTMLElement).closest("a")) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const y = e.clientY - rect.top;
    const start = yToMinutes(y);
    dragRef.current = { active: true, dayIso, startMinutes: start, currentMinutes: start + MIN_SNAP };
    setDragVersion((v) => v + 1);
  }
  function onMouseMoveCell(e: React.MouseEvent) {
    if (!dragRef.current.active) return;
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const y = e.clientY - rect.top;
    const m = yToMinutes(y);
    if (m !== dragRef.current.currentMinutes) {
      dragRef.current.currentMinutes = m;
      setDragVersion((v) => v + 1);
    }
  }
  function onMouseUpCell() {
    if (!dragRef.current.active) return;
    const { dayIso, startMinutes, currentMinutes } = dragRef.current;
    const from = Math.min(startMinutes, currentMinutes);
    const to = Math.max(startMinutes, currentMinutes);
    const duration = Math.max(MIN_SNAP, to - from);
    dragRef.current.active = false;
    setDragVersion((v) => v + 1);
    const startDate = new Date(dayIso + "T00:00:00");
    startDate.setMinutes(from);
    const endDate = new Date(startDate.getTime() + duration * 60000);
    onCreate(startDate, endDate);
  }

  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 0, overflowX: "auto" }}>
      <div style={{ display: "grid", gridTemplateColumns: "60px repeat(" + days + ", minmax(" + (days === 7 ? "120px" : "300px") + ", 1fr))", minWidth: days === 7 ? 900 : "auto" }}>
        <div style={{ borderBottom: "1px solid #eef1f5" }} />
        {dayList.map((d) => {
          const iso = isoDate(d);
          const isToday = iso === nowIso;
          return (
            <button key={iso} onClick={() => onDayHeader && onDayHeader(d)} style={{ borderBottom: "1px solid #eef1f5", background: "transparent", border: 0, borderLeft: "1px solid #f1f4f8", padding: "10px 6px", textAlign: "center", cursor: onDayHeader ? "pointer" : "default" }}>
              <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 700, color: "#8b97a9" }}>{DAYS_SHORT[d.getDay() === 0 ? 6 : d.getDay() - 1]}</div>
              <div style={{ fontSize: 22, fontWeight: 700, marginTop: 2, color: isToday ? "#5b5cf0" : "#17213a" }}>{d.getDate()}</div>
            </button>
          );
        })}
        <div style={{ position: "relative", height: gridHeight }}>
          {HOURS.map((h) => (
            <div key={h} style={{ height: CELL_H, fontSize: 11, color: "#8b97a9", textAlign: "right", paddingRight: 8, paddingTop: 2 }}>{fmtHM(h, 0)}</div>
          ))}
        </div>
        {dayList.map((d) => {
          const iso = isoDate(d);
          const dayEvents = eventsByDay[iso] || [];
          const isTodayCol = iso === nowIso;
          return (
            <div key={iso} style={{ position: "relative", height: gridHeight, borderLeft: "1px solid #f1f4f8" }}
              onMouseDown={(e) => onMouseDownCell(e, iso)} onMouseMove={onMouseMoveCell} onMouseUp={onMouseUpCell}
              onMouseLeave={() => { if (dragRef.current.active) onMouseUpCell(); }}>
              {HOURS.map((h) => (<div key={h} style={{ height: CELL_H, borderTop: "1px solid #f1f4f8" }} />))}
              {dragRef.current.active && dragRef.current.dayIso === iso && (() => {
                const from = Math.min(dragRef.current.startMinutes, dragRef.current.currentMinutes);
                const to = Math.max(dragRef.current.startMinutes, dragRef.current.currentMinutes);
                const top = ((from - gridStart) / 60) * CELL_H;
                const height = ((to - from) / 60) * CELL_H;
                return <div style={{ position: "absolute", left: 2, right: 2, top, height: Math.max(6, height), background: "rgba(91,92,240,0.18)", border: "2px dashed #5b5cf0", borderRadius: 6, pointerEvents: "none", zIndex: 20 }} />;
              })()}
              {dayEvents.map((e, i) => {
                const c = eventColour(e);
                const startM = new Date(e.at).getHours() * 60 + new Date(e.at).getMinutes();
                const endM = e.ends_at ? new Date(e.ends_at).getHours() * 60 + new Date(e.ends_at).getMinutes() : startM + 30;
                const top = ((startM - gridStart) / 60) * CELL_H;
                const height = Math.max(20, ((endM - startM) / 60) * CELL_H - 2);
                return (
                  <a key={i} href="#" onClick={(ev) => { ev.preventDefault(); ev.stopPropagation(); onEdit(e); }}
                    title={fmtTime(new Date(e.at)) + (e.ends_at ? " – " + fmtTime(new Date(e.ends_at)) : "") + " · " + e.title}
                    style={{ position: "absolute", left: 3, right: 3, top: Math.max(0, top), height, background: c.bg, color: c.fg, borderLeft: "3px solid " + c.border, borderRadius: 5, padding: "3px 6px", fontSize: 11, textDecoration: "none", overflow: "hidden", zIndex: 10, fontWeight: 600, lineHeight: 1.25 }}>
                    <div style={{ fontWeight: 700, opacity: 0.85 }}>{fmtTime(new Date(e.at))}</div>
                    <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{e.title}</div>
                  </a>
                );
              })}
              {isTodayCol && nowMinutes >= gridStart && nowMinutes <= gridEnd && (
                <div style={{ position: "absolute", left: 0, right: 0, top: ((nowMinutes - gridStart) / 60) * CELL_H, height: 2, background: "#c74646", zIndex: 15, pointerEvents: "none" }}>
                  <span style={{ position: "absolute", left: -5, top: -4, width: 10, height: 10, borderRadius: 5, background: "#c74646" }} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TaskModal({ task, status, saving, onChange, onSave, onDelete, onClose }: any) {
  function update(k: string, v: any) { onChange({ ...task, [k]: v }); }
  const start = new Date(task.start);
  const end = new Date(task.end);
  const durationMin = Math.max(0, Math.round((end.getTime() - start.getTime()) / 60000));
  const dh = Math.floor(durationMin / 60);
  const dm = durationMin % 60;
  const durationLabel = (dh > 0 ? dh + "h " : "") + (dm > 0 ? dm + "m" : dh > 0 ? "" : "0m");

  function setStart(iso: string) {
    const oldDuration = end.getTime() - start.getTime();
    const ns = new Date(iso);
    const ne = new Date(ns.getTime() + oldDuration);
    onChange({ ...task, start: ns.toISOString(), end: ne.toISOString() });
  }
  function setEnd(iso: string) {
    onChange({ ...task, end: new Date(iso).toISOString() });
  }
  function toLocalInput(d: Date) {
    const pad = (n: number) => String(n).padStart(2, "0");
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  return (
    <div style={modalBackdrop} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={modalBox}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <h2 style={{ margin: 0, fontSize: 16, color: "#17213a" }}>{task.id ? "Edit task" : "New task"}</h2>
          <button onClick={onClose} style={{ background: "transparent", border: 0, color: "#8490a4", fontSize: 22, cursor: "pointer", lineHeight: 1 }}>×</button>
        </div>
        <input value={task.title} onChange={(e) => update("title", e.target.value)} placeholder="Add title" autoFocus style={{ display: "block", width: "100%", padding: 12, border: "1px solid #d7dce5", borderRadius: 10, fontSize: 15, outline: "none", marginBottom: 14, fontWeight: 600 }} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
          <label style={labelStyle}>Start<input type="datetime-local" value={toLocalInput(start)} onChange={(e) => setStart(new Date(e.target.value).toISOString())} style={inputStyle} /></label>
          <label style={labelStyle}>End<input type="datetime-local" value={toLocalInput(end)} onChange={(e) => setEnd(new Date(e.target.value).toISOString())} style={inputStyle} /></label>
        </div>
        <p style={{ margin: "0 0 14px", fontSize: 11, color: "#8490a4" }}>Duration: <b>{durationLabel}</b></p>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#4b5563", marginBottom: 14 }}>
          <input type="checkbox" checked={!!task.all_day} onChange={(e) => update("all_day", e.target.checked)} style={{ width: "auto", margin: 0 }} />
          All day
        </label>
        <label style={labelStyle}>Notes<textarea value={task.notes} onChange={(e) => update("notes", e.target.value)} rows={4} placeholder="Details, context, follow-up questions…" style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }} /></label>
        <label style={labelStyle}>Priority
          <select value={task.priority} onChange={(e) => update("priority", e.target.value)} style={inputStyle}>
            <option value="low">Low (grey)</option>
            <option value="normal">Normal (blue)</option>
            <option value="high">High (orange)</option>
            <option value="urgent">Urgent (red)</option>
          </select>
        </label>
        {status && <p style={{ margin: "6px 0", fontSize: 12, color: "#1aa76c" }}>{status}</p>}
        <div style={{ display: "flex", gap: 10, marginTop: 18, justifyContent: "space-between" }}>
          <div>{onDelete && <button onClick={onDelete} style={{ ...ghostBtn, color: "#c74646", borderColor: "#f0c6c6" }}>Delete</button>}</div>
          <div style={{ display: "flex", gap: 10 }}>
            <button onClick={onClose} style={ghostBtn}>Cancel</button>
            <button onClick={onSave} disabled={saving} style={primaryBtn}>{saving ? "Saving…" : "Save"}</button>
          </div>
        </div>
      </div>
    </div>
  );
}

function SidePanel({ dayIso, monthData, tasks, onClose, onCreate }: any) {
  const day = monthData?.days.find((d: any) => d.date === dayIso);
  const dayTasks = (tasks || []).filter((t: any) => t.due_at?.slice(0, 10) === dayIso);
  const d = new Date(dayIso + "T00:00:00");
  function addTask() { const start = new Date(dayIso + "T09:00:00"); onCreate(start); }
  return (
    <div style={{ width: 320, flexShrink: 0, background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20, position: "sticky", top: 90 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 10, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700 }}>{d.toLocaleDateString(undefined, { weekday: "long" })}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#17213a", marginTop: 2 }}>{d.toLocaleDateString(undefined, { day: "numeric", month: "long" })}</div>
        </div>
        <button onClick={onClose} style={{ background: "transparent", border: 0, color: "#8490a4", fontSize: 20, cursor: "pointer", lineHeight: 1 }}>×</button>
      </div>
      <button onClick={addTask} style={{ width: "100%", background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "10px 16px", borderRadius: 10, fontWeight: 700, fontSize: 12, cursor: "pointer", marginBottom: 16 }}>+ Add task on this day</button>
      {dayTasks.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, color: "#8b95a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 8 }}>Tasks ({dayTasks.length})</div>
          {dayTasks.map((t: any) => {
            const c = t.priority === "urgent" ? "#c74646" : t.priority === "high" ? "#e99132" : t.priority === "low" ? "#8490a4" : "#566ce1";
            return (
              <div key={t.id} style={{ background: "#fafbfd", borderLeft: "3px solid " + c, borderRadius: 6, padding: "8px 10px", fontSize: 12, marginBottom: 6 }}>
                <div style={{ fontWeight: 600, color: "#17213a" }}>{t.title}</div>
                <div style={{ fontSize: 10, color: "#8b95a5", marginTop: 2 }}>{new Date(t.due_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · {t.duration_minutes || 30} min</div>
              </div>
            );
          })}
        </div>
      )}
      {day && (day.orders > 0 || day.calls > 0) && (
        <div>
          <div style={{ fontSize: 10, color: "#8b95a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 8 }}>Activity</div>
          {day.orders > 0 && <div style={{ fontSize: 12, color: "#4b5563", padding: "4px 0" }}>Orders: <b>{day.orders}</b></div>}
          {day.calls > 0 && <div style={{ fontSize: 12, color: "#4b5563", padding: "4px 0" }}>AI calls: <b>{day.calls}</b></div>}
        </div>
      )}
      {(!day || (day.orders === 0 && day.calls === 0)) && dayTasks.length === 0 && (
        <p style={{ margin: 0, fontSize: 12, color: "#8490a4" }}>Nothing scheduled on this day.</p>
      )}
    </div>
  );
}

function Legend() {
  const items = [
    { label: "Confirmed", colour: "#1d9c68" },
    { label: "In progress", colour: "#e99132" },
    { label: "Cancelled / missed", colour: "#c74646" },
    { label: "Completed (past)", colour: "#8490a4" },
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

const navBtn: React.CSSProperties = { background: "#fff", border: "1px solid #d7dce5", width: 38, height: 38, borderRadius: 10, fontSize: 18, cursor: "pointer", color: "#17213a" };
const dateInput: React.CSSProperties = { padding: "8px 10px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 13, background: "#fff", outline: "none" };
const loadingBox: React.CSSProperties = { padding: 60, textAlign: "center", color: "#75839a", background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14 };
const labelStyle: React.CSSProperties = { display: "block", fontSize: 12, fontWeight: 600, color: "#17213a", marginBottom: 12 };
const inputStyle: React.CSSProperties = { display: "block", width: "100%", marginTop: 6, padding: 10, borderRadius: 8, border: "1px solid #d7dce5", fontSize: 13, outline: "none" };
const primaryBtn: React.CSSProperties = { background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: "pointer" };
const ghostBtn: React.CSSProperties = { background: "#fff", color: "#17213a", border: "1px solid #e5e7eb", padding: "11px 22px", borderRadius: 10, fontWeight: 600, fontSize: 13, cursor: "pointer" };
const modalBackdrop: React.CSSProperties = { position: "fixed", inset: 0, background: "rgba(7,21,46,0.5)", backdropFilter: "blur(4px)", zIndex: 100, display: "grid", placeItems: "center", padding: 20 };
const modalBox: React.CSSProperties = { width: "min(560px, 100%)", background: "#fff", borderRadius: 16, padding: 24, boxShadow: "0 25px 70px rgba(7,21,46,0.25)", maxHeight: "90vh", overflowY: "auto" };
'''

TARGET.write_text(CONTENT, encoding="utf-8")
print(f"File saved: {TARGET.stat().st_size} bytes")
print(f"Location: {TARGET}")