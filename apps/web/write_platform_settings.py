"""Write the platform settings page."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "platform" / "settings" / "page.tsx"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = '''"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PlatformSettings() {
  const [settings, setSettings] = useState<any>(null);
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
    fetch(api() + "/api/v1/platform/settings", {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
    })
      .then((r) => {
        if (r.status === 401 || r.status === 403) { window.location.href = "/login"; throw new Error("auth"); }
        return r.json();
      })
      .then((x) => { setSettings(x); setLoading(false); })
      .catch((e) => { if (e.message !== "auth") setError(e.message || "Failed to load"); setLoading(false); });
  }, []);

  function set(key: string, value: any) {
    setSettings((s: any) => ({ ...s, [key]: value }));
  }

  async function save() {
    setSaving(true); setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/settings", {
        method: "PUT",
        headers: headers(),
        body: JSON.stringify({ updates: settings }),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Save failed");
      setSettings(x);
      setStatus("Settings saved");
    } catch (e: any) { setStatus(e.message); }
    setSaving(false);
  }

  if (loading) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  if (error) return <div style={{ padding: 40, color: "#b00" }}>{error}</div>;
  if (!settings) return null;

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>Platform Settings</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>Global configuration for the whole platform.</p>
      </div>

      <Section title="Company identity">
        <Field label="Company name"><input value={settings.company_name || ""} onChange={(e) => set("company_name", e.target.value)} style={inputStyle} /></Field>
        <Field label="Company email"><input value={settings.company_email || ""} onChange={(e) => set("company_email", e.target.value)} style={inputStyle} /></Field>
        <Field label="Company phone"><input value={settings.company_phone || ""} onChange={(e) => set("company_phone", e.target.value)} style={inputStyle} /></Field>
        <Field label="Support email"><input value={settings.support_email || ""} onChange={(e) => set("support_email", e.target.value)} style={inputStyle} /></Field>
        <Field label="Billing email"><input value={settings.billing_email || ""} onChange={(e) => set("billing_email", e.target.value)} style={inputStyle} /></Field>
        <Field label="Contact email"><input value={settings.contact_email || ""} onChange={(e) => set("contact_email", e.target.value)} style={inputStyle} /></Field>
      </Section>

      <Section title="SLA turnaround (hours)">
        <Field label="Support"><input type="number" value={settings.sla_support_hours || 24} onChange={(e) => set("sla_support_hours", Number(e.target.value))} style={inputStyle} /></Field>
        <Field label="Billing"><input type="number" value={settings.sla_billing_hours || 4} onChange={(e) => set("sla_billing_hours", Number(e.target.value))} style={inputStyle} /></Field>
        <Field label="Contact"><input type="number" value={settings.sla_contact_hours || 48} onChange={(e) => set("sla_contact_hours", Number(e.target.value))} style={inputStyle} /></Field>
        <Field label="Critical"><input type="number" value={settings.sla_critical_hours || 2} onChange={(e) => set("sla_critical_hours", Number(e.target.value))} style={inputStyle} /></Field>
      </Section>

      <Section title="Alert channels">
        <Toggle label="Email" checked={!!settings.alerts_email_enabled} onChange={(v) => set("alerts_email_enabled", v)} />
        <Toggle label="SMS" checked={!!settings.alerts_sms_enabled} onChange={(v) => set("alerts_sms_enabled", v)} />
        <Toggle label="WhatsApp" checked={!!settings.alerts_whatsapp_enabled} onChange={(v) => set("alerts_whatsapp_enabled", v)} />
        <Field label="Alert recipients (comma-separated)">
          <input value={settings.alert_recipients || ""} onChange={(e) => set("alert_recipients", e.target.value)} style={inputStyle} placeholder="admin@aigrowthos.com, ops@aigrowthos.com" />
        </Field>
      </Section>

      <Section title="Business hours">
        <Field label="Opens at"><input value={settings.business_hours_start || "09:00"} onChange={(e) => set("business_hours_start", e.target.value)} style={inputStyle} placeholder="09:00" /></Field>
        <Field label="Closes at"><input value={settings.business_hours_end || "18:00"} onChange={(e) => set("business_hours_end", e.target.value)} style={inputStyle} placeholder="18:00" /></Field>
        <Field label="Working days (1=Mon ... 7=Sun)"><input value={settings.business_days || "1,2,3,4,5"} onChange={(e) => set("business_days", e.target.value)} style={inputStyle} /></Field>
        <Field label="Timezone"><input value={settings.timezone || "Asia/Kolkata"} onChange={(e) => set("timezone", e.target.value)} style={inputStyle} /></Field>
      </Section>

      <Section title="Platform toggles">
        <Toggle label="Signups enabled" checked={!!settings.signups_enabled} onChange={(v) => set("signups_enabled", v)} />
        <Toggle label="Maintenance mode" checked={!!settings.maintenance_mode} onChange={(v) => set("maintenance_mode", v)} />
        <Field label="Maintenance message"><input value={settings.maintenance_message || ""} onChange={(e) => set("maintenance_message", e.target.value)} style={inputStyle} /></Field>
      </Section>

      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <button onClick={save} disabled={saving} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "12px 26px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: saving ? "wait" : "pointer" }}>
          {saving ? "Saving…" : "Save settings"}
        </button>
        <span style={{ fontSize: 12, color: "#1aa76c" }}>{status}</span>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24, marginBottom: 18 }}>
      <h2 style={{ margin: "0 0 16px", fontSize: 15, color: "#17213a" }}>{title}</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 14 }}>{children}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
      {label}
      {children}
    </label>
  );
}

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13, color: "#17213a", cursor: "pointer" }}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} style={{ width: "auto", margin: 0 }} />
      {label}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  display: "block",
  width: "100%",
  marginTop: 6,
  padding: 10,
  borderRadius: 8,
  border: "1px solid #d7dce5",
  fontSize: 13,
  outline: "none",
};
'''

TARGET.write_text(CONTENT, encoding="utf-8")
print(f"File saved: {TARGET.stat().st_size} bytes")
print(f"Location: {TARGET}")