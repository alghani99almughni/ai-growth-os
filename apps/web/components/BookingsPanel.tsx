"use client";
import { useEffect, useRef, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Appointment = {
  id: string;
  customer_id: string;
  service_id: string | null;
  service_name: string | null;
  staff_id: string | null;
  staff_name: string | null;
  starts_at: string;
  ends_at: string;
  timezone: string;
  status: string;
  source: string;
  notes: string | null;
  queue_token: string | null;
  queue_status: string | null;
  queue: { token: string; status: string; people_ahead: number; estimated_wait_minutes: number } | null;
};

type QueueItem = {
  id: string;
  appointment_id: string;
  token: string;
  status: string;
  people_ahead: number;
  estimated_wait_minutes: number;
  customer_id: string;
};

const STATUS_COLOURS: Record<string, string> = {
  requested: "badge-orange",
  confirmed: "badge-blue",
  checked_in: "badge-purple",
  serving: "badge-purple",
  completed: "badge-grey",
  cancelled: "badge-grey",
  no_show: "badge-grey",
};

function todayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

// Backend returns naive UTC ("2026-09-30T10:00:00"). Parse it as UTC,
// then render in the tenant's timezone so the user sees local wall-clock time.
function fmtTime(iso: string, tz: string): string {
  try {
    const u = iso.endsWith("Z") ? iso : iso + "Z";
    const d = new Date(u);
    return d.toLocaleTimeString("en-IN", {
      timeZone: tz || undefined,
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    });
  } catch {
    return iso;
  }
}

function fmtRange(a: Appointment): string {
  return `${fmtTime(a.starts_at, a.timezone)} – ${fmtTime(a.ends_at, a.timezone)}`;
}

export default function BookingsPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [date, setDate] = useState<string>(todayIso());
  const [items, setItems] = useState<Appointment[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState<string>("");
  const [confirmationAlert, setConfirmationAlert] = useState("");
  const [appointmentAlertTitle, setAppointmentAlertTitle] = useState("Appointment update");
  const previousStatuses = useRef<Record<string, { status: string; starts_at: string }> | null>(null);

  const authHeaders = () => ({ Authorization: "Bearer " + token });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
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
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll(silent = false) {
    if (!silent) { setLoading(true); setError(""); }
    try {
      const [listRes, queueRes] = await Promise.all([
        jget(`/api/v1/tenants/${tenantId}/appointments?date=${date}`),
        jget(`/api/v1/tenants/${tenantId}/queue?date=${date}`).catch(() => ({ items: [] })),
      ]);
      const nextItems: Appointment[] = listRes.items || [];
      const previous = previousStatuses.current;
      if (silent && previous) {
        const newlyCancelled = nextItems.find((a) => a.status === "cancelled" && previous[a.id]?.status !== "cancelled");
        const newlyConfirmed = nextItems.find((a) => a.status === "confirmed" && previous[a.id]?.status !== "confirmed");
        const rescheduled = nextItems.find((a) => previous[a.id] && previous[a.id].starts_at !== a.starts_at && a.status !== "cancelled");
        const disappeared = Object.keys(previous).find((id) => !nextItems.some((a) => a.id === id));
        if (newlyCancelled) {
          setAppointmentAlertTitle("Appointment cancelled");
          setConfirmationAlert(`${newlyCancelled.service_name || "Appointment"} · ${fmtRange(newlyCancelled)}`);
        } else if (rescheduled) {
          setAppointmentAlertTitle("Appointment rescheduled");
          setConfirmationAlert(`${rescheduled.service_name || "Appointment"} · new time ${fmtRange(rescheduled)}`);
        } else if (newlyConfirmed) {
          setAppointmentAlertTitle("Appointment confirmed");
          setConfirmationAlert(`${newlyConfirmed.service_name || "Appointment"} · ${fmtRange(newlyConfirmed)}`);
        } else if (disappeared) {
          setAppointmentAlertTitle("Appointment moved or removed");
          setConfirmationAlert("An appointment no longer appears on this date. Refresh or check the customer's new appointment date.");
        }
      }
      previousStatuses.current = Object.fromEntries(nextItems.map((a) => [a.id, { status: a.status, starts_at: a.starts_at }]));
      setItems(nextItems);
      setQueue(queueRes.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load bookings");
    }
    if (!silent) setLoading(false);
  }

  useEffect(() => {
    if (!tenantId) return;
    void loadAll();
    // Keep a bookings tab current when an AI call creates or changes an appointment.
    const refresh = () => {
      if (document.visibilityState === "visible") void loadAll(true);
    };
    const timer = window.setInterval(refresh, 10000);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
    // loadAll intentionally reads the current tenant/date from this render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, date]);

  async function setStatusFor(a: Appointment, newStatus: string) {
    setStatus("");
    setBusyId(a.id);
    try {
      await jsend(
        `/api/v1/tenants/${tenantId}/appointments/${a.id}`,
        "PATCH",
        { status: newStatus }
      );
      setStatus(`Updated to ${newStatus}`);
      await loadAll();
    } catch (e: any) {
      setStatus(e.message || "Update failed");
    }
    setBusyId("");
  }

  async function checkIn(a: Appointment) {
    setStatus("");
    setBusyId(a.id);
    try {
      await jsend(
        `/api/v1/tenants/${tenantId}/appointments/${a.id}/queue`,
        "POST",
        {}
      );
      setStatus(`Checked in · token ${a.queue_token || ""}`);
      await loadAll();
    } catch (e: any) {
      setStatus(e.message || "Check-in failed");
    }
    setBusyId("");
  }

  return (
    <section className="card">
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2 style={{ margin: 0 }}>📅 Bookings</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            Appointments and live queue for the selected date.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            style={{
              padding: "8px 10px",
              border: "1px solid #d7dde8",
              borderRadius: 8,
              fontSize: 13,
            }}
          />
          <button className="btn-ghost" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>
      </div>

      {error && <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>}
      {confirmationAlert && (
        <div role="alert" aria-live="assertive" style={{ marginTop: 12, padding: "12px 14px", borderRadius: 8, border: "1px solid #9ad6ad", background: "#effaf2", color: "#14532d", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <strong>✓ {appointmentAlertTitle}</strong>
          <span>{confirmationAlert}</span>
          <button className="btn-ghost" onClick={() => setConfirmationAlert("")} aria-label="Dismiss appointment update alert">Dismiss</button>
        </div>
      )}

      {/* Appointments list */}
      <div style={{ marginTop: 24 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
          Appointments ({items.length})
        </h3>

        {items.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No appointments</h3>
            <p>Nothing booked for {date}. Try another date or create one from the PWA.</p>
          </div>
        )}

        {items.map((a) => (
          <article
            key={a.id}
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
                  <strong style={{ fontSize: 15 }}>{fmtRange(a)}</strong>
                  <span className={"badge " + (STATUS_COLOURS[a.status] || "badge-grey")}>
                    {a.status.replace("_", " ")}
                  </span>
                  {a.queue_token && (
                    <span className="badge badge-purple">queue · {a.queue_token}</span>
                  )}
                </div>
                <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                  {a.service_name || <em>No service</em>}
                  {a.staff_name ? <> · with <strong style={{ color: "#17213a" }}>{a.staff_name}</strong></> : null}
                  {" · customer "}
                  <span style={{ fontFamily: "monospace", fontSize: 11 }}>
                    {a.customer_id.slice(0, 8)}
                  </span>
                </p>
                {a.notes && (
                  <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                    Notes: {a.notes}
                  </p>
                )}
                {a.queue && (
                  <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                    In queue · {a.queue.people_ahead} ahead · ~{a.queue.estimated_wait_minutes} min
                  </p>
                )}
              </div>

              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {a.status === "requested" && (
                  <button
                    className="btn-ghost"
                    disabled={busyId === a.id}
                    onClick={() => setStatusFor(a, "confirmed")}
                  >
                    Confirm
                  </button>
                )}
                {(a.status === "confirmed" || a.status === "requested") && (
                  <button
                    className="btn-ghost"
                    disabled={busyId === a.id}
                    onClick={() => checkIn(a)}
                  >
                    Check in
                  </button>
                )}
                {a.status === "checked_in" && (
                  <button
                    className="btn-primary"
                    disabled={busyId === a.id}
                    onClick={() => setStatusFor(a, "serving")}
                  >
                    Start
                  </button>
                )}
                {a.status === "serving" && (
                  <button
                    className="btn-primary"
                    disabled={busyId === a.id}
                    onClick={() => setStatusFor(a, "completed")}
                  >
                    Complete
                  </button>
                )}
                {a.status !== "completed" && a.status !== "cancelled" && a.status !== "no_show" && (
                  <>
                    <button
                      className="btn-ghost"
                      disabled={busyId === a.id}
                      onClick={() => setStatusFor(a, "no_show")}
                    >
                      No-show
                    </button>
                    <button
                      className="btn-ghost"
                      style={{ color: "#c74646", borderColor: "#f0c6c6" }}
                      disabled={busyId === a.id}
                      onClick={() => setStatusFor(a, "cancelled")}
                    >
                      Cancel
                    </button>
                  </>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>

      {/* Live queue */}
      <div
        style={{
          marginTop: 24,
          paddingTop: 20,
          borderTop: "1px solid #eef1f5",
        }}
      >
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
          Live queue · {date}
        </h3>
        {queue.length === 0 && (
          <p style={{ color: "#75839a", fontSize: 13 }}>Queue is empty.</p>
        )}
        {queue.length > 0 && (
          <div>
            {queue.map((q) => (
              <div
                key={q.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "8px 0",
                  fontSize: 13,
                  borderBottom: "1px solid #f1f4f8",
                }}
              >
                <span>
                  <strong>{q.token}</strong> ·{" "}
                  <span className={"badge " + (STATUS_COLOURS[q.status] || "badge-grey")}>
                    {q.status}
                  </span>
                </span>
                <span style={{ color: "#75839a" }}>
                  {q.people_ahead} ahead · ~{q.estimated_wait_minutes} min
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {status && (
        <p aria-live="polite" style={{ marginTop: 16, fontSize: 12, color: "#1aa76c" }}>
          {status}
        </p>
      )}
    </section>
  );
}