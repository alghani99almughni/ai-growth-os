"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type DayRow = { open: string; close: string; closed: boolean; allDay: boolean };
const DEFAULT_ROWS: DayRow[] = DAYS.map((_, i) => ({
  open: "09:00",
  close: i === 6 ? "13:00" : "18:00",
  closed: i === 6,
  allDay: false,
}));

type Industry = { key: string; label: string };

export default function OnboardingPage() {
  const router = useRouter();

  const [step, setStep] = useState(1);
  const [industries, setIndustries] = useState<Industry[]>([]);
  const [industry, setIndustry] = useState("cafe");

  const [businessName, setBusinessName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [rows, setRows] = useState<DayRow[]>(DEFAULT_ROWS);

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState<{ slug: string; pwa: string } | null>(null);

  useEffect(() => {
    fetch(API + "/api/v1/public/industries")
      .then((r) => r.json())
      .then((x) => setIndustries(x.items || []))
      .catch(() => setIndustries([
        { key: "cafe", label: "Cafe" },
        { key: "restaurant", label: "Restaurant" },
        { key: "salon", label: "Salon" },
        { key: "dental", label: "Dental Clinic" },
        { key: "gym", label: "Gym / Fitness" },
        { key: "health", label: "Health / Clinic" },
        { key: "wellness", label: "Wellness" },
        { key: "hotel", label: "Hotel" },
        { key: "real-estate", label: "Real Estate" },
        { key: "education", label: "Education" },
      ]));
  }, []);

  function upd(i: number, patch: Partial<DayRow>) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  function next() {
    setErr("");
    if (step === 1) {
      if (!industry) return setErr("Please pick an industry.");
      setStep(2);
    } else if (step === 2) {
      if (!businessName.trim()) return setErr("Business name is required.");
      if (!ownerName.trim() || !ownerEmail.trim() || ownerPassword.length < 8) {
        return setErr("Owner name, email, and password (8+ chars) are required.");
      }
      setStep(3);
    }
  }

  function back() {
    setErr("");
    setStep((s) => Math.max(1, s - 1));
  }

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const res = await fetch(API + "/api/v1/public/onboard/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          business_name: businessName.trim(),
          industry,
          owner_name: ownerName.trim(),
          owner_email: ownerEmail.trim(),
          owner_password: ownerPassword,
          phone: phone.trim() || null,
          whatsapp_number: phone.trim() || null,
          address: address.trim() || null,
          timezone: "Asia/Kolkata",
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
      if (!res.ok) throw new Error(data.detail || "Signup failed.");
      setResult({
        slug: data.slug,
        pwa: `https://ai-growth-os-web.onrender.com${data.customer_pwa_url}`,
      });
      setStep(4);
    } catch (e: any) {
      setErr(String(e?.message || "Signup failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f5f7fb", padding: "40px 20px" }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <header style={{ marginBottom: 24 }}>
          <h1 style={{ margin: 0, fontSize: 28, color: "#17213a", letterSpacing: "-0.03em" }}>
            Get your business online in 3 minutes
          </h1>
          <p style={{ marginTop: 6, color: "#75839a", fontSize: 14 }}>
            Sign up once. Your dashboard, customer PWA, and AI assistant are ready instantly.
          </p>
        </header>

        <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              style={{
                flex: 1,
                height: 4,
                borderRadius: 2,
                background: step >= n ? "#5b5cf0" : "#e5e9f0",
                transition: "background 0.2s",
              }}
            />
          ))}
        </div>

        <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 28 }}>
          {step === 1 && (
            <>
              <h2 style={{ margin: 0, fontSize: 18, color: "#17213a" }}>What kind of business?</h2>
              <p style={{ margin: "6px 0 20px", color: "#75839a", fontSize: 13 }}>
                We&apos;ll set up the right defaults for you.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10 }}>
                {industries.map((it) => (
                  <button
                    key={it.key}
                    type="button"
                    onClick={() => setIndustry(it.key)}
                    style={{
                      padding: "14px 16px",
                      border: "1px solid " + (industry === it.key ? "#5b5cf0" : "#e8ecf3"),
                      background: industry === it.key ? "#f5f4ff" : "#fff",
                      borderRadius: 10,
                      cursor: "pointer",
                      fontSize: 14,
                      fontWeight: 600,
                      color: "#17213a",
                      textAlign: "left",
                    }}
                  >
                    {it.label}
                  </button>
                ))}
              </div>
            </>
          )}

          {step === 2 && (
            <>
              <h2 style={{ margin: 0, fontSize: 18, color: "#17213a" }}>Business and owner details</h2>
              <p style={{ margin: "6px 0 20px", color: "#75839a", fontSize: 13 }}>
                This is how your dashboard and customer PWA will be labelled.
              </p>
              <Field label="Business name">
                <input value={businessName} onChange={(e) => setBusinessName(e.target.value)} style={input} placeholder="SS Nutritions" />
              </Field>
              <Field label="Your name">
                <input value={ownerName} onChange={(e) => setOwnerName(e.target.value)} style={input} placeholder="Syed Shukur" />
              </Field>
              <Field label="Email">
                <input type="email" value={ownerEmail} onChange={(e) => setOwnerEmail(e.target.value)} style={input} placeholder="you@business.com" />
              </Field>
              <Field label="Password (min 8 characters)">
                <input type="password" value={ownerPassword} onChange={(e) => setOwnerPassword(e.target.value)} style={input} placeholder="••••••••" />
              </Field>
              <Field label="Phone (optional)">
                <input value={phone} onChange={(e) => setPhone(e.target.value)} style={input} placeholder="+91 90000 00000" />
              </Field>
              <Field label="Address (optional)">
                <input value={address} onChange={(e) => setAddress(e.target.value)} style={input} placeholder="Moinabad, Rangareddy" />
              </Field>
            </>
          )}

          {step === 3 && (
            <>
              <h2 style={{ margin: 0, fontSize: 18, color: "#17213a" }}>Business hours</h2>
              <p style={{ margin: "6px 0 20px", color: "#75839a", fontSize: 13 }}>
                You can change these any time from your dashboard.
              </p>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr>
                    <th style={th}>Day</th>
                    <th style={th}>Open</th>
                    <th style={th}>Close</th>
                    <th style={{ ...th, textAlign: "center" }}>24h</th>
                    <th style={{ ...th, textAlign: "center" }}>Closed</th>
                  </tr>
                </thead>
                <tbody>
                  {DAYS.map((d, i) => (
                    <tr key={d}>
                      <td style={td}>{d}</td>
                      <td style={td}>
                        <input type="time" value={rows[i].open} disabled={rows[i].allDay || rows[i].closed} onChange={(e) => upd(i, { open: e.target.value })} style={smallInput} />
                      </td>
                      <td style={td}>
                        <input type="time" value={rows[i].close} disabled={rows[i].allDay || rows[i].closed} onChange={(e) => upd(i, { close: e.target.value })} style={smallInput} />
                      </td>
                      <td style={{ ...td, textAlign: "center" }}>
                        <input type="checkbox" checked={rows[i].allDay} onChange={(e) => upd(i, { allDay: e.target.checked, closed: e.target.checked ? false : rows[i].closed })} />
                      </td>
                      <td style={{ ...td, textAlign: "center" }}>
                        <input type="checkbox" checked={rows[i].closed} disabled={rows[i].allDay} onChange={(e) => upd(i, { closed: e.target.checked })} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {step === 4 && result && (
            <>
              <div style={{ textAlign: "center" }}>
                <div style={{ width: 56, height: 56, borderRadius: 28, background: "#e7f8f0", display: "grid", placeItems: "center", margin: "0 auto 12px", fontSize: 28 }}>✓</div>
                <h2 style={{ margin: 0, fontSize: 20, color: "#17213a" }}>You&apos;re ready</h2>
                <p style={{ margin: "8px 0 24px", color: "#75839a", fontSize: 13 }}>
                  Your business is set up. Sign in to your dashboard to see everything.
                </p>
                <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
                  <button type="button" onClick={() => router.push("/login")} style={primary}>
                    Go to dashboard
                  </button>
                  <a href={result.pwa} target="_blank" rel="noreferrer" style={{ ...secondary, textDecoration: "none" }}>
                    Preview customer PWA
                  </a>
                </div>
                <p style={{ marginTop: 20, fontSize: 12, color: "#98a2b4" }}>
                  Your slug: <code style={{ background: "#f5f7fb", padding: "2px 8px", borderRadius: 6 }}>{result.slug}</code>
                </p>
              </div>
            </>
          )}

          {err && <p style={{ marginTop: 16, color: "#b00", fontSize: 13 }}>{err}</p>}

          {step < 4 && (
            <div style={{ display: "flex", gap: 10, justifyContent: "space-between", marginTop: 24 }}>
              <button type="button" onClick={back} disabled={step === 1} style={{ ...secondary, opacity: step === 1 ? 0.5 : 1, cursor: step === 1 ? "default" : "pointer" }}>
                Back
              </button>
              {step < 3 ? (
                <button type="button" onClick={next} style={primary}>
                  Continue
                </button>
              ) : (
                <button type="button" onClick={submit} disabled={busy} style={{ ...primary, opacity: busy ? 0.7 : 1, cursor: busy ? "wait" : "pointer" }}>
                  {busy ? "Creating…" : "Create my business"}
                </button>
              )}
            </div>
          )}
        </div>

        <p style={{ textAlign: "center", marginTop: 24, color: "#98a2b4", fontSize: 12 }}>
          Already have an account? <a href="/login" style={{ color: "#5b5cf0", fontWeight: 600, textDecoration: "none" }}>Sign in</a>
        </p>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block", marginTop: 12 }}>
      <span style={{ display: "block", fontSize: 12, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 600, marginBottom: 6 }}>{label}</span>
      {children}
    </label>
  );
}

const input: React.CSSProperties = {
  width: "100%", padding: "11px 14px", border: "1px solid #d7dce5", borderRadius: 10, fontSize: 14, color: "#17213a", background: "#fff", outline: "none", boxSizing: "border-box",
};

const smallInput: React.CSSProperties = { ...input, padding: "8px 10px", fontSize: 13 };

const primary: React.CSSProperties = {
  background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "12px 22px", borderRadius: 10, fontWeight: 700, fontSize: 14, cursor: "pointer",
};

const secondary: React.CSSProperties = {
  background: "#fff", color: "#17213a", border: "1px solid #d7dce5", padding: "12px 22px", borderRadius: 10, fontWeight: 600, fontSize: 14, cursor: "pointer",
};

const th: React.CSSProperties = {
  textAlign: "left", padding: "8px 10px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5",
};

const td: React.CSSProperties = {
  padding: "6px 10px", color: "#4b5563", fontSize: 13,
};