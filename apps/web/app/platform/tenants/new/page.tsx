"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
const INDUSTRIES = ["restaurant","cafe","hotel","salon","dental","gym","health","wellness","real-estate","education"];

type DayRow = { open: string; close: string; closed: boolean; allDay: boolean };
const DEFAULT_ROWS: DayRow[] = DAYS.map((_, i) => ({ open: "09:00", close: i === 6 ? "13:00" : "18:00", closed: i === 6, allDay: false }));

export default function NewTenantPage() {
  const router = useRouter();
  const [businessName, setBusinessName] = useState("");
  const [industry, setIndustry] = useState("wellness");
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [whatsapp, setWhatsapp] = useState("");
  const [address, setAddress] = useState("");
  const [rows, setRows] = useState<DayRow[]>(DEFAULT_ROWS);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState<{ slug: string; id: string } | null>(null);

  const upd = (i: number, patch: Partial<DayRow>) => {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  };

  const submit = async () => {
    setErr(""); setOk(null);
    if (!businessName.trim()) return setErr("Business name is required.");
    if (!ownerName.trim() || !ownerEmail.trim() || ownerPassword.length < 8) return setErr("Owner name, email and password (8+) are required.");
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
          phone: phone.trim() || null,
          whatsapp_number: whatsapp.trim() || null,
          address: address.trim() || null,
          business_hours: rows.map((r, i) => ({
            weekday: i,
            open_time: r.allDay ? "00:00" : r.open,
            close_time: r.allDay ? "23:59" : r.close,
            is_closed: r.closed && !r.allDay,
            is_24_hours: r.allDay,
            slot_interval_minutes: 30,
          })),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Unable to create tenant.");
      setOk({ slug: data.tenant.slug, id: data.tenant.id });
      setBusinessName(""); setOwnerName(""); setOwnerEmail(""); setOwnerPassword("");
      setPhone(""); setWhatsapp(""); setAddress(""); setRows(DEFAULT_ROWS);
    } catch (e: any) {
      setErr(String(e?.message || "Unable to create tenant."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 720 }}>
      <h1 style={{ margin: "0 0 6px" }}>Create Tenant</h1>
      <p style={{ color: "#5a7268", marginTop: 0 }}>Provision a new business. Slug is generated automatically.</p>

      <section style={{ display: "grid", gap: 10, marginBottom: 20 }}>
        <label>Business name<input value={businessName} onChange={(e) => setBusinessName(e.target.value)} /></label>
        <label>Industry
          <select value={industry} onChange={(e) => setIndustry(e.target.value)}>
            {INDUSTRIES.map((x) => <option key={x} value={x}>{x}</option>)}
          </select>
        </label>
        <label>Owner name<input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} /></label>
        <label>Owner email<input type="email" value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} /></label>
        <label>Owner password<input type="password" value={ownerPassword} onChange={(e) => setOwnerPassword(e.target.value)} /></label>
        <label>Phone<input value={phone} onChange={(e) => setPhone(e.target.value)} /></label>
        <label>WhatsApp<input value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)} /></label>
        <label>Address<textarea value={address} onChange={(e) => setAddress(e.target.value)} rows={2} /></label>
      </section>

      <h3 style={{ margin: "12px 0 6px" }}>Business hours</h3>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr><th align="left">Day</th><th align="left">Open</th><th align="left">Close</th><th>24h</th><th>Closed</th></tr>
        </thead>
        <tbody>
          {DAYS.map((d, i) => (
            <tr key={d}>
              <td style={{ padding: "4px 0" }}>{d}</td>
              <td><input type="time" value={rows[i].open} disabled={rows[i].allDay || rows[i].closed} onChange={(e) => upd(i, { open: e.target.value })} /></td>
              <td><input type="time" value={rows[i].close} disabled={rows[i].allDay || rows[i].closed} onChange={(e) => upd(i, { close: e.target.value })} /></td>
              <td align="center"><input type="checkbox" checked={rows[i].allDay} onChange={(e) => upd(i, { allDay: e.target.checked, closed: e.target.checked ? false : rows[i].closed })} /></td>
              <td align="center"><input type="checkbox" checked={rows[i].closed} disabled={rows[i].allDay} onChange={(e) => upd(i, { closed: e.target.checked })} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      {err && <p style={{ color: "#b6341f", marginTop: 12 }}>{err}</p>}
      {ok && (
        <p style={{ color: "#0b6b3a", marginTop: 12 }}>
          Tenant created. Slug: <b>{ok.slug}</b>.{" "}
          <a href={`https://ai-growth-os-web.onrender.com/customer?business=${ok.slug}`} target="_blank" rel="noreferrer">Open Customer PWA →</a>
        </p>
      )}

      <button disabled={busy} onClick={submit} style={{ marginTop: 16, padding: "10px 18px", background: "#1a5c43", color: "#fff", border: 0, borderRadius: 10, fontWeight: 700 }}>
        {busy ? "Creating…" : "Create Tenant"}
      </button>
    </div>
  );
}