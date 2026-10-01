"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Staff = {
  id: string;
  name: string;
  user_id?: string | null;
  department_id?: string | null;
  department_name?: string | null;
  email?: string | null;
  role?: string | null;
  skills: string | null;
  is_active: boolean;
  is_available: boolean;
};

function parseSkills(raw: string | null): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function TeamPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [items, setItems] = useState<Staff[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const authHeaders = () => ({ Authorization: "Bearer " + token });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const res = await jget(`/api/v1/tenants/${tenantId}/staff`);
      setItems(res.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load team members");
    }
    setLoading(false);
  }

  useEffect(() => {
    if (tenantId) void loadAll();
  }, [tenantId]);

  return (
    <section className="card">
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
          <h2 style={{ margin: 0 }}>🧑‍💼 Team</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            {items.length} team member{items.length === 1 ? "" : "s"}.
          </p>
        </div>
        <button className="btn-ghost" onClick={loadAll} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>}

      <div style={{ marginTop: 20 }}>
        {items.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No team members yet</h3>
            <p>Add staff so they can be assigned to bookings and calls.</p>
          </div>
        )}

        {items.map((s) => {
          const skills = parseSkills(s.skills);
          return (
            <article
              key={s.id}
              className="card"
              style={{ marginBottom: 10, padding: 14, background: "#fff" }}
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
                    <strong style={{ fontSize: 14 }}>{s.name}</strong>
                    {s.is_available ? (
                      <span className="badge badge-blue">available</span>
                    ) : (
                      <span className="badge badge-grey">unavailable</span>
                    )}
                    {!s.is_active && <span className="badge badge-grey">inactive</span>}
                    {s.role && <span className="badge badge-purple">{s.role}</span>}
                    {s.department_name && (
                      <span className="badge badge-grey">{s.department_name}</span>
                    )}
                  </div>
                  {s.email && (
                    <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                      ✉️ {s.email}
                    </p>
                  )}
                  {skills.length > 0 && (
                    <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                      Skills: {skills.join(", ")}
                    </p>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      <p style={{ marginTop: 20, fontSize: 12, color: "#98a2b4" }}>
        Add team members, manage departments, set availability — coming in v2.
      </p>
    </section>
  );
}