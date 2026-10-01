"""Shrink calendar cells and re-add the right side preview panel."""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "platform" / "calendar" / "page.tsx"

if not TARGET.exists():
    print("ERROR: calendar page not found")
    sys.exit(1)

text = TARGET.read_text(encoding="utf-8")

# 1. Shrink month cells
text = text.replace("minHeight: 110", "minHeight: 88")
# 2. Shrink hour cell
text = text.replace("const CELL_H = 48;", "const CELL_H = 42;")

# 3. Add sidePanel state to the main component (after sidePanelOpen removal in v2)
if "const [sidePanel, setSidePanel]" not in text:
    anchor = 'const [modalOpen, setModalOpen] = useState(false);'
    new = anchor + '\n  const [sidePanel, setSidePanel] = useState<string | null>(null);'
    if anchor in text:
        text = text.replace(anchor, new, 1)
        print("added sidePanel state")

# 4. In MonthView, add onSelect to also set sidePanel - change the onCreate call
old_month_click = '''            <div key={d.date} onClick={(e) => {
              const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
              const x = e.clientX - rect.left;
              const y = e.clientY - rect.top;
              // estimate hour from click position within the cell
              const hour = Math.max(6, Math.min(21, 6 + Math.floor((y / rect.height) * 16)));
              const start = new Date(d.date + "T" + String(hour).padStart(2, "0") + ":00:00");
              onCreate(start);
            }}'''
new_month_click = '''            <div key={d.date} onClick={(e) => {
              // click on empty cell area = open side panel; click on "+" = quick create
              onSelectDay && onSelectDay(d.date);
            }}'''
if old_month_click in text:
    text = text.replace(old_month_click, new_month_click, 1)
    print("MonthView now opens side panel on click")

# 5. Pass onSelectDay to MonthView
old_month_call = '<MonthView data={monthData} onCreate={openCreate} onEdit={openEdit} />'
new_month_call = '<MonthView data={monthData} onCreate={openCreate} onEdit={openEdit} onSelectDay={setSidePanel} />'
text = text.replace(old_month_call, new_month_call)

# 6. Pass onSelectDay in MonthView signature
text = text.replace(
    "function MonthView({ data, onCreate, onEdit }: any) {",
    "function MonthView({ data, onCreate, onEdit, onSelectDay }: any) {"
)

# 7. Wrap the main content area in a flex row that includes the side panel
old_layout = '''      {loading ? (
        <div style={loadingBox}>Loading…</div>
      ) : view === "month" ? (
        <MonthView data={monthData} onCreate={openCreate} onEdit={openEdit} onSelectDay={setSidePanel} />
      ) : view === "week" ? (
        <TimeGridView anchor={anchor} events={events} days={7} onCreate={openCreate} onEdit={openEdit} onDayHeader={(d) => { setAnchor(d); setView("day"); }} />
      ) : (
        <TimeGridView anchor={anchor} events={events} days={1} onCreate={openCreate} onEdit={openEdit} onDayHeader={null} />
      )}'''

new_layout = '''      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
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
      </div>'''

if old_layout in text:
    text = text.replace(old_layout, new_layout, 1)
    print("side panel wired into layout")
else:
    print("WARNING: main layout block not found — the side panel wasn't added")

# 8. Append the SidePanel component before the Legend function
side_panel_jsx = '''
function SidePanel({ dayIso, monthData, tasks, onClose, onCreate }: any) {
  const day = monthData?.days.find((d: any) => d.date === dayIso);
  const dayTasks = (tasks || []).filter((t: any) => t.due_at?.slice(0, 10) === dayIso);
  const d = new Date(dayIso + "T00:00:00");

  function addTask() {
    const start = new Date(dayIso + "T09:00:00");
    onCreate(start);
  }

  return (
    <div style={{ width: 320, flexShrink: 0, background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20, position: "sticky", top: 90 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 10, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700 }}>
            {d.toLocaleDateString(undefined, { weekday: "long" })}
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: "#17213a", marginTop: 2 }}>
            {d.toLocaleDateString(undefined, { day: "numeric", month: "long" })}
          </div>
        </div>
        <button onClick={onClose} style={{ background: "transparent", border: 0, color: "#8490a4", fontSize: 20, cursor: "pointer", lineHeight: 1 }}>×</button>
      </div>

      <button onClick={addTask} style={{ width: "100%", background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "10px 16px", borderRadius: 10, fontWeight: 700, fontSize: 12, cursor: "pointer", marginBottom: 16 }}>
        + Add task on this day
      </button>

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

      {day && (day.signups?.length > 0 || day.orders > 0 || day.calls > 0) && (
        <div>
          <div style={{ fontSize: 10, color: "#8b95a9", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 8 }}>Activity</div>
          {day.signups?.length > 0 && day.signups.map((s: any) => (
            <a key={s.id} href={"/platform/tenants/" + s.id} style={{ display: "block", padding: "8px 10px", borderRadius: 6, background: "#edf2ff", color: "#3448b8", textDecoration: "none", fontSize: 12, marginBottom: 4, fontWeight: 600 }}>
              New signup: {s.name}
            </a>
          ))}
          {day.orders > 0 && <div style={{ fontSize: 12, color: "#4b5563", padding: "4px 0" }}>Orders: <b>{day.orders}</b></div>}
          {day.calls > 0 && <div style={{ fontSize: 12, color: "#4b5563", padding: "4px 0" }}>AI calls: <b>{day.calls}</b></div>}
        </div>
      )}

      {(!day || (!day.signups?.length && !day.orders && !day.calls)) && dayTasks.length === 0 && (
        <p style={{ margin: 0, fontSize: 12, color: "#8490a4" }}>Nothing scheduled on this day.</p>
      )}
    </div>
  );
}

'''

if "function SidePanel(" not in text:
    legend_anchor = "function Legend() {"
    if legend_anchor in text:
        text = text.replace(legend_anchor, side_panel_jsx + legend_anchor, 1)
        print("SidePanel component added")
    else:
        print("WARNING: Legend function not found — could not insert SidePanel")
else:
    print("SidePanel already exists")

TARGET.write_text(text, encoding="utf-8")
print("Calendar updated: smaller cells + side panel")