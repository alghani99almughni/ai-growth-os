"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

const INDUSTRIES = [
  { key: "restaurant", label: "Restaurant" },
  { key: "cafe", label: "Cafe" },
  { key: "hotel", label: "Hotel" },
  { key: "salon", label: "Salon" },
  { key: "dental", label: "Dental Clinic" },
  { key: "gym", label: "Gym / Fitness" },
  { key: "health", label: "Health / Clinic" },
  { key: "wellness", label: "Wellness" },
  { key: "real-estate", label: "Real Estate" },
  { key: "education", label: "Education" },
];

export default function NewTenantPage() {
  const router = useRouter();

  const [businessName, setBusinessName] = useState("");
  const [industry, setIndustry] = useState("wellness");
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [contactNumber, setContactNumber] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [website, setWebsite] = useState("");
  const [address, setAddress] = useState("");

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const submit = async () => {
    setErr("");
    if (!businessName.trim()) return setErr("Business name is required.");
    if (!ownerName.trim() || !ownerEmail.trim() || ownerPassword.length < 8)
      return setErr("Owner name, email, and password (8+ chars) are required.");
    if (!contactNumber.trim()) return setErr("Contact number is required.");
    if (!whatsappNumber.trim()) return setErr("WhatsApp number is required.");

    setBusy(true);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("ago_access_token") || "" : "";
      const res = await fetch(`${API}/api/v1/platform/tenants/provision`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          business_name: businessName.trim(),
          slug: null,
          industry,
          owner_name: ownerName.trim(),
          owner_email: ownerEmail.trim(),
          owner_password: ownerPassword,
          phone: contactNumber.trim(),
          whatsapp_number: whatsappNumber.trim(),
          address: address.trim() || null,
          website: website.trim() || null,
          template: null,
          business_hours: null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Unable to create tenant.");
      router.push(`/platform/tenants/${data.tenant.id}`);
    } catch (e: any) {
      setErr(String(e?.message || "Unable to create tenant."));
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ margin: "0 0 6px" }}>Create Tenant</h1>
      <p style={{ color: "#5a7268", marginTop: 0 }}>
        Provision a new business. Slug is generated automatically. Business hours and integrations are configured after creation.
      </p>

      <section style={{ display: "grid", gap: 12, marginBottom: 20 }}>
        <Field label="Business category">
          <select value={industry} onChange={(e) => setIndustry(e.target.value)} style={inp}>
            {INDUSTRIES.map((x) => (
              <option key={x.key} value={x.key}>{x.label}</option>
            ))}
          </select>
        </Field>

        <Field label="Business name">
          <input value={businessName} onChange={(e) => setBusinessName(e.target.value)} placeholder="Test Biz" style={inp} />
        </Field>

        <hr style={{ border: 0, borderTop: "1px solid #e8ecf3", margin: "6px 0" }} />

        <Field label="Owner name">
          <input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} placeholder="Test Owner" style={inp} />
        </Field>

        <Field label="Owner email (used to sign in)">
          <input type="email" value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} placeholder="tenant@example.com" style={inp} />
        </Field>

        <Field label="Owner password (8+ characters)">
          <input type="password" value={ownerPassword} onChange={(e) => setOwnerPassword(e.target.value)} style={inp} />
        </Field>

        <hr style={{ border: 0, borderTop: "1px solid #e8ecf3", margin: "6px 0" }} />

        <Field label="Contact number">
          <input value={contactNumber} onChange={(e) => setContactNumber(e.target.value)} placeholder="+91 98765 43210" style={inp} />
        </Field>

        <Field label="WhatsApp number">
          <input value={whatsappNumber} onChange={(e) => setWhatsappNumber(e.target.value)} placeholder="+91 98765 43210" style={inp} />
        </Field>

        <Field label="Existing website (optional)">
          <input value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="https://theirbusiness.com" style={inp} />
          <div style={{ fontSize: 11, color: "#75839a", marginTop: 4 }}>
            Leave blank if they don&apos;t have one — we&apos;ll generate a webpage for them.
          </div>
        </Field>

        <Field label="Address (optional)">
          <textarea value={address} onChange={(e) => setAddress(e.target.value)} rows={2} style={{ ...inp, fontFamily: "inherit" }} />
        </Field>
      </section>

      {err && <p style={{ color: "#b6341f", marginBottom: 12 }}>{err}</p>}

      <button
        disabled={busy}
        onClick={submit}
        style={{ padding: "12px 24px", background: "#1a5c43", color: "#fff", border: 0, borderRadius: 10, fontWeight: 700, fontSize: 14, cursor: busy ? "wait" : "pointer", opacity: busy ? 0.7 : 1 }}
      >
        {busy ? "Creating…" : "Create Tenant"}
      </button>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block" }}>
      <span style={{ display: "block", fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginBottom: 5 }}>{label}</span>
      {children}
    </label>
  );
}

const inp: React.CSSProperties = {
  display: "block", width: "100%", padding: "11px 13px", border: "1px solid #d7dce5",
  borderRadius: 9, fontSize: 14, color: "#17213a", background: "#fff", outline: "none", boxSizing: "border-box",
};