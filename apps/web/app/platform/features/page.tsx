"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const FEATURE_LABELS: Record<string, string> = {
  digital_menu: "Digital menu",
  online_ordering: "Online ordering",
  order_tracking: "Order tracking",
  call_waiter: "Call waiter",
  service_requests: "Service requests",
  games: "Mini games",
  auto_bill: "Auto bill",
  online_payment: "Online payment",
  ai_chat: "AI chat",
  ai_voice: "AI voice",
  loyalty: "Loyalty",
  referrals: "Referrals",
  feedback: "Feedback",
  google_review: "Google review",
  bookings: "Bookings",
  queue: "Queue",
};

export default function FeatureDefaultsPage() {
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  function headers() {
    return {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || ""),
    };
  }

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) { window.location.href = "/login"; return; }
    fetch(api() + "/api/v1/platform/feature-defaults", {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
    })
      .then((r) => {
        if (r.status === 401 || r.status === 403) { window.location.href = "/login"; throw new Error("auth"); }
        return r.json();
      })
      .then((x) => { setFeatures(x.features || {}); setLoading(false); })
      .catch((e) => { if (e.message !== "auth") setError(e.message || "Failed to load"); setLoading(false); });
  }, []);

  function toggle(k: string, v: boolean) {
    setFeatures((f) => ({ ...f, [k]: v }));
  }

  async function save() {
    setSaving(true);
    setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/feature-defaults", {
        method: "PUT",
        headers: headers(),
        body: JSON.stringify({ features }),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Save failed");
      setFeatures(x.features || {});
      setStatus("Defaults saved");
    } catch (e: any) {
      setStatus(e.message);
    }
    setSaving(false);
  }

  if (loading) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  if (error) return <div style={{ padding: 40, color: "#b00" }}>{error}</div>;

  const enabledCount = Object.values(features).filter(Boolean).length;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Feature Defaults</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          {enabledCount} of {Object.keys(FEATURE_LABELS).length} features enabled by default for new tenants.
        </p>
      </div>

      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24, marginBottom: 18 }}>
        <h2 style={{ margin: "0 0 6px", fontSize: 15, color: "#17213a" }}>Platform defaults</h2>
        <p style={{ margin: "0 0 16px", color: "#75839a", fontSize: 13 }}>
          These apply to new tenants when they sign up. Existing tenants keep their own settings.
          Individual tenants can be overridden from their detail page.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
          {Object.keys(FEATURE_LABELS).map((k) => (
            <label
              key={k}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                padding: 12,
                border: "1px solid " + (features[k] ? "#5b5cf0" : "#e8ecf3"),
                background: features[k] ? "#f5f4ff" : "#fff",
                borderRadius: 10,
                cursor: "pointer",
                transition: "all 0.12s",
              }}
            >
              <input
                type="checkbox"
                checked={!!features[k]}
                onChange={(e) => toggle(k, e.target.checked)}
                style={{ width: "auto", margin: 0 }}
              />
              <span style={{ fontSize: 13, color: "#17213a", fontWeight: 500 }}>{FEATURE_LABELS[k]}</span>
            </label>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <button onClick={save} disabled={saving} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "12px 26px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: saving ? "wait" : "pointer" }}>
          {saving ? "Saving…" : "Save defaults"}
        </button>
        <span style={{ fontSize: 12, color: "#1aa76c" }}>{status}</span>
      </div>
    </div>
  );
}
