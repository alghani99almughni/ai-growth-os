"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const FEATURE_KEYS = ["digital_menu","online_ordering","order_tracking","call_waiter","service_requests","games","auto_bill","online_payment","ai_chat","ai_voice","loyalty","referrals","feedback","google_review","bookings","queue"];

const tok = () => (typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : "");
const hdr = () => ({ "Content-Type": "application/json", Authorization: `Bearer ${tok()}` });

export default function TenantDetailPage() {
  const params = useParams();
  const id = String(params?.id || "");
  const [detail, setDetail] = useState<any>(null);
  const [features, setFeatures] = useState<Record<string, boolean>>({});
  const [activity, setActivity] = useState<any>(null);
  const [whatsapp, setWhatsapp] = useState<any>(null);
  const [razorpay, setRazorpay] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => { if (id) void load(); }, [id]);

  const load = async () => {
    setErr("");
    try {
      const [d, f, a, w, r] = await Promise.all([
        fetch(`${API}/api/v1/platform/tenants/${id}/detail`, { headers: hdr() }).then((x) => x.json()),
        fetch(`${API}/api/v1/platform/tenants/${id}/overrides`, { headers: hdr() }).then((x) => x.json()),
        fetch(`${API}/api/v1/platform/tenants/${id}/activity`, { headers: hdr() }).then((x) => x.json()),
        fetch(`${API}/api/v1/platform/tenants/${id}/whatsapp`, { headers: hdr() }).then((x) => x.json()),
        fetch(`${API}/api/v1/platform/tenants/${id}/razorpay`, { headers: hdr() }).then((x) => x.json()),
      ]);
      setDetail(d); setFeatures(f.features || {}); setActivity(a); setWhatsapp(w); setRazorpay(r);
    } catch (e: any) { setErr(String(e?.message || "Load failed.")); }
  };

  const saveFeatures = async () => {
    setBusy(true); setErr("");
    try {
      const res = await fetch(`${API}/api/v1/platform/tenants/${id}/overrides`, { method: "PUT", headers: hdr(), body: JSON.stringify({ features }) });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Save failed.");
      setFeatures(data.features || features);
    } catch (e: any) { setErr(String(e?.message || "Save failed.")); }
    finally { setBusy(false); }
  };

  if (!detail) return <p style={{ padding: 20 }}>{err || "Loading…"}</p>;

  return (
    <div style={{ maxWidth: 900 }}>
      <h1 style={{ margin: "0 0 6px" }}>{detail.name}</h1>
      <p style={{ color: "#5a7268", marginTop: 0 }}>
        {detail.industry} · {detail.status} · {detail.timezone}
      </p>
      <p>
        <a href={`https://ai-growth-os-web.onrender.com/customer?business=${detail.slug}`} target="_blank" rel="noreferrer">
          Open Customer PWA →
        </a>
      </p>

      <h3>Health</h3>
      <p>Score: <b>{detail.health_score?.score ?? "—"}</b> · Band: <b>{detail.health_score?.band ?? "—"}</b></p>

      <h3>Activity (30d)</h3>
      <pre style={{ background: "#f6f8f6", padding: 12, borderRadius: 8, overflow: "auto" }}>{JSON.stringify(activity, null, 2)}</pre>

      <h3>Feature overrides</h3>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0,1fr))", gap: 8 }}>
        {FEATURE_KEYS.map((k) => (
          <label key={k} style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="checkbox" checked={!!features[k]} onChange={(e) => setFeatures((p) => ({ ...p, [k]: e.target.checked }))} />
            {k}
          </label>
        ))}
      </div>
      <button disabled={busy} onClick={saveFeatures} style={{ marginTop: 12, padding: "8px 16px", background: "#1a5c43", color: "#fff", border: 0, borderRadius: 8, fontWeight: 700 }}>
        {busy ? "Saving…" : "Save features"}
      </button>

      <h3 style={{ marginTop: 24 }}>WhatsApp</h3>
      <pre style={{ background: "#f6f8f6", padding: 12, borderRadius: 8, overflow: "auto" }}>{JSON.stringify(whatsapp, null, 2)}</pre>

      <h3>Razorpay</h3>
      <pre style={{ background: "#f6f8f6", padding: 12, borderRadius: 8, overflow: "auto" }}>{JSON.stringify(razorpay, null, 2)}</pre>

      {err && <p style={{ color: "#b6341f" }}>{err}</p>}
    </div>
  );
}