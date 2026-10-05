"use client";

import { useEffect, useState } from "react";
import WebCallRuntimeModal from "../../../components/WebCallRuntimeModal";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const PILOT_TENANT_ID = "1f11597e-602e-43a5-a550-4779aaa21ad6";
const PILOT_SLUG = "ss-nutritions";

export default function WebCallPilotPage() {
  const [business, setBusiness] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(
          API + "/api/v1/public/business/" + encodeURIComponent(PILOT_SLUG),
          { cache: "no-store" }
        );
        const data = await r.json().catch(() => ({}));
        if (!r.ok || !data?.id) throw new Error(data?.detail || "Pilot tenant could not be loaded.");
        if (!cancelled) setBusiness(data);
      } catch (e: any) {
        if (!cancelled) setError(e?.message || "Unable to load pilot tenant.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <main className="shell">
        <section className="hero">
          <p>AI GROWTH OS · WEB CALL PILOT</p>
          <h1>Loading pilot tenant…</h1>
          <p>Tenant: {PILOT_TENANT_ID}</p>
        </section>
      </main>
    );
  }

  if (error || !business) {
    return (
      <main className="shell">
        <section className="hero">
          <p>AI GROWTH OS · WEB CALL PILOT</p>
          <h1>Pilot unavailable</h1>
          <p>{error || "Tenant not found."}</p>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <section className="hero">
        <p>AI GROWTH OS · SINGLE TENANT PILOT</p>
        <h1>{business.name}</h1>
        <p>
          Isolated Web Call Runtime test. This page does not replace the production
          customer Call button and does not affect other tenants.
        </p>
        <div className="card" style={{ marginTop: 20, textAlign: "left" }}>
          <strong>Tenant</strong>
          <div>{business.name}</div>
          <small>{PILOT_TENANT_ID}</small>
        </div>
        <button
          onClick={() => setOpen(true)}
          disabled={!business.features?.ai_voice}
          style={{ marginTop: 20, fontSize: 16, padding: "14px 22px", borderRadius: 12 }}
        >
          📞 Test Call AI
        </button>
        {!business.features?.ai_voice && (
          <p style={{ marginTop: 10 }}>AI Voice is disabled for this tenant.</p>
        )}
      </section>

      {open && <WebCallRuntimeModal onClose={() => setOpen(false)} />}
    </main>
  );
}
