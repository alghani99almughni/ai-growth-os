"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Headphones, PhoneCall, ShieldCheck } from "lucide-react";
import VoiceCallModal from "../../../components/VoiceCallModal";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PublicVoiceEntry() {
  const params = useParams<{ slug: string }>();
  const slug = params?.slug || "";
  const [business, setBusiness] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [callOpen, setCallOpen] = useState(false);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!slug) return;
    fetch(api() + "/api/v1/public/business/" + encodeURIComponent(slug), { cache: "no-store" })
      .then(r => r.ok ? r.json() : Promise.reject(new Error("This business voice page is unavailable.")))
      .then(data => setBusiness(data))
      .catch(e => setError(e.message || "Unable to load this business."))
      .finally(() => setLoading(false));
  }, [slug]);

  const name = business?.name || business?.business_name || "Business";
  const description = business?.description || "Ask a question, request a service or speak with our team.";
  const accent = "#2547b8";

  return <main style={{ minHeight: "100vh", background: "linear-gradient(145deg,#f5f7fc,#eaf0fb)", display: "grid", placeItems: "center", padding: 20, color: "#14233b" }}>
    <section style={{ width: "100%", maxWidth: 470, background: "#fff", border: "1px solid #e4eaf3", borderRadius: 24, padding: "34px 28px", boxShadow: "0 24px 80px rgba(24,45,86,.10)", textAlign: "center" }}>
      <div style={{ width: 64, height: 64, margin: "0 auto 18px", borderRadius: 20, background: "#edf2ff", display: "grid", placeItems: "center", color: accent }}><Headphones size={30}/></div>
      <div style={{ color: accent, fontSize: 10, fontWeight: 800, letterSpacing: 2 }}>AI VOICE ASSISTANT</div>
      <h1 style={{ fontSize: 28, fontWeight: 850, marginTop: 10 }}>{loading ? "Connecting…" : name}</h1>
      <p style={{ color: "#64748b", fontSize: 14, lineHeight: 1.6, marginTop: 10 }}>{description}</p>
      {error && <p role="alert" style={{ color: "#b42318", background: "#fff0ef", padding: 10, borderRadius: 9, marginTop: 16, fontSize: 13 }}>{error}</p>}
      <button disabled={loading || !!error || !business} onClick={() => setCallOpen(true)} style={{ width: "100%", marginTop: 26, padding: "15px 18px", background: accent, color: "#fff", border: 0, borderRadius: 13, fontWeight: 800, fontSize: 15, display: "flex", alignItems: "center", justifyContent: "center", gap: 10, opacity: loading || !!error ? .55 : 1 }}>
        <PhoneCall size={18}/> Start a voice call
      </button>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 7, color: "#64748b", fontSize: 11, marginTop: 16 }}><ShieldCheck size={14}/> Your call may be recorded to improve service, subject to the business's consent notice.</div>
      <p style={{ color: "#94a3b8", fontSize: 10, marginTop: 24 }}>Powered by AI Growth OS</p>
    </section>
    {callOpen && business && <VoiceCallModal slug={slug} businessName={name} existingCustomerId={customerId} onCustomerIdentified={setCustomerId} onClose={() => setCallOpen(false)} />}
  </main>;
}
