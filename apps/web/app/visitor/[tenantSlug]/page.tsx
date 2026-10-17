"use client";

import { FormEvent, useState } from "react";
import { useParams } from "next/navigation";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PublicVisitorEntryPage() {
  const params = useParams<{ tenantSlug: string }>();
  const tenantSlug = String(params?.tenantSlug || "").toLowerCase();
  const [name, setName] = useState("");
  const [mobile, setMobile] = useState("");
  const [purpose, setPurpose] = useState("");
  const [destination, setDestination] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ticket, setTicket] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setTicket("");
    try {
      const response = await fetch(
        api() + "/api/v1/public/smartcheck/" + encodeURIComponent(tenantSlug) + "/visitor-requests",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            visitor_name: name.trim(),
            visitor_mobile: mobile.trim(),
            purpose: purpose.trim(),
            destination: destination.trim(),
            vehicle_number: vehicle.trim(),
          }),
        },
      );
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || "Unable to submit visitor request.");
      setTicket(String(result.ticket_id || ""));
      setName("");
      setMobile("");
      setPurpose("");
      setDestination("");
      setVehicle("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to submit visitor request.");
    } finally {
      setBusy(false);
    }
  }

  const input: React.CSSProperties = {
    width: "100%", boxSizing: "border-box", marginTop: 6, padding: "12px 13px",
    border: "1px solid #d6deea", borderRadius: 10, fontSize: 15, background: "#fff",
  };
  const label: React.CSSProperties = { display: "block", marginTop: 15, fontSize: 13, fontWeight: 650, color: "#24324a" };

  return (
    <main style={{ minHeight: "100vh", padding: "28px 16px", background: "#f4f7fb", color: "#17213a" }}>
      <section style={{ maxWidth: 520, margin: "0 auto", padding: 24, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 18, boxShadow: "0 12px 36px rgba(25,45,80,.07)" }}>
        <div style={{ fontSize: 11, letterSpacing: ".12em", textTransform: "uppercase", color: "#64748b", fontWeight: 750 }}>Visitor entry</div>
        <h1 style={{ fontSize: 27, lineHeight: 1.2, margin: "8px 0" }}>Register your visit</h1>
        <p style={{ color: "#64748b", fontSize: 14, lineHeight: 1.6, marginTop: 0 }}>
          Submit your details for security approval. Installing the PWA is not required. Do not enter sensitive ID or payment information in this form.
        </p>

        {error && <div role="alert" style={{ padding: 12, margin: "14px 0", borderRadius: 10, background: "#fff1f1", color: "#a12626", fontSize: 13 }}>{error}</div>}
        {ticket && <div role="status" style={{ padding: 14, margin: "14px 0", borderRadius: 10, background: "#effaf4", color: "#176044", fontSize: 14 }}>
          <strong>Request submitted</strong>
          <p style={{ margin: "6px 0" }}>Reference: <strong>{ticket}</strong></p>
          Your request is pending approval. This reference is not an entry pass; please wait for security or your host to confirm.
        </div>}

        <form onSubmit={submit}>
          <label style={label}>Full name *
            <input required maxLength={160} autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} style={input} placeholder="Enter your name" />
          </label>
          <label style={label}>Mobile number *
            <input required minLength={5} maxLength={32} inputMode="tel" autoComplete="tel" value={mobile} onChange={(e) => setMobile(e.target.value)} style={input} placeholder="Enter mobile number" />
          </label>
          <label style={label}>Purpose of visit
            <input maxLength={240} value={purpose} onChange={(e) => setPurpose(e.target.value)} style={input} placeholder="Meeting, delivery, parent visit…" />
          </label>
          <label style={label}>Person / department / destination
            <input maxLength={200} value={destination} onChange={(e) => setDestination(e.target.value)} style={input} placeholder="Who are you visiting?" />
          </label>
          <label style={label}>Vehicle number (optional)
            <input maxLength={40} value={vehicle} onChange={(e) => setVehicle(e.target.value)} style={input} placeholder="Vehicle registration" />
          </label>
          <button type="submit" disabled={busy || !tenantSlug} style={{ width: "100%", marginTop: 22, padding: 13, border: 0, borderRadius: 10, background: busy ? "#8390a4" : "#1d4ed8", color: "#fff", fontWeight: 700, fontSize: 15, cursor: busy ? "wait" : "pointer" }}>
            {busy ? "Submitting…" : "Submit for approval"}
          </button>
        </form>
        <p style={{ fontSize: 11, color: "#748198", lineHeight: 1.5, marginBottom: 0, marginTop: 16 }}>
          Your information is used to process this visit request. Entry is controlled by authorized site staff.
        </p>
      </section>
    </main>
  );
}
