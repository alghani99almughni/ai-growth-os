"""Write the platform AI providers page."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "app" / "platform" / "ai" / "page.tsx"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = '''"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AiProvidersPage() {
  const [providers, setProviders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    provider: "gemini",
    model: "",
    api_key: "",
    priority: 100,
    enabled: true,
  });

  function headers() {
    return {
      "Content-Type": "application/json",
      Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || ""),
    };
  }

  async function load() {
    setLoading(true);
    try {
      const r = await fetch(api() + "/api/v1/platform/ai/providers", {
        headers: { Authorization: "Bearer " + (localStorage.getItem("ago_access_token") || "") },
        cache: "no-store",
      });
      if (r.status === 401 || r.status === 403) { window.location.href = "/login"; return; }
      const x = await r.json();
      setProviders(x.providers || []);
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  }

  useEffect(() => { void load(); }, []);

  async function addProvider(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setStatus("");
    try {
      const r = await fetch(api() + "/api/v1/platform/ai/providers", {
        method: "POST",
        headers: headers(),
        body: JSON.stringify(form),
      });
      const x = await r.json();
      if (!r.ok) throw new Error(x?.detail || "Failed to add provider");
      setStatus("Provider added: " + form.provider + "/" + form.model);
      setForm({ provider: "gemini", model: "", api_key: "", priority: 100, enabled: true });
      void load();
    } catch (e: any) {
      setStatus(e.message);
    }
    setSaving(false);
  }

  async function recover(p: any) {
    try {
      const r = await fetch(
        api() + "/api/v1/platform/ai/providers/" + encodeURIComponent(p.provider) + "/recover?model=" + encodeURIComponent(p.model),
        { method: "POST", headers: headers() }
      );
      if (!r.ok) throw new Error("Reset failed");
      setStatus("Cooldown reset: " + p.provider + "/" + p.model);
      void load();
    } catch (e: any) {
      setStatus(e.message);
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>AI Providers</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Platform-level AI provider pool. Tenants can also bring their own keys.
        </p>
      </div>

      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24, marginBottom: 18 }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 15, color: "#17213a" }}>Add a provider</h2>
        <form onSubmit={addProvider} style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
            Provider
            <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} style={inputStyle}>
              {["gemini", "openai", "openrouter", "anthropic"].map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
            Model
            <input required value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder="gemini-2.5-flash" style={inputStyle} />
          </label>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
            API Key
            <input required type="password" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} style={inputStyle} />
          </label>
          <label style={{ fontSize: 12, fontWeight: 600, color: "#17213a" }}>
            Priority
            <input type="number" value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} style={inputStyle} />
          </label>
          <div style={{ alignSelf: "end" }}>
            <button type="submit" disabled={saving} style={primaryBtn}>
              {saving ? "Adding…" : "Add provider"}
            </button>
          </div>
        </form>
        {status && <p style={{ margin: "14px 0 0", fontSize: 12, color: "#1aa76c" }}>{status}</p>}
      </div>

      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24 }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 15, color: "#17213a" }}>Provider usage ({providers.length})</h2>

        {loading && <p style={{ color: "#75839a", fontSize: 13 }}>Loading…</p>}
        {error && <p style={{ color: "#b00", fontSize: 13 }}>{error}</p>}

        {!loading && providers.length === 0 && (
          <p style={{ color: "#75839a", fontSize: 13 }}>No providers configured yet.</p>
        )}

        {providers.length > 0 && (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead style={{ background: "#fafbfd" }}>
              <tr>
                <th style={thStyle}>Provider / Model</th>
                <th style={thStyle}>Tenant</th>
                <th style={thStyle}>Requests</th>
                <th style={thStyle}>Failures</th>
                <th style={thStyle}>Rate limits</th>
                <th style={thStyle}>Cooldown</th>
                <th style={thStyle}>Action</th>
              </tr>
            </thead>
            <tbody>
              {providers.map((p, i) => (
                <tr key={i} style={{ borderTop: "1px solid #f1f4f8" }}>
                  <td style={tdStyle}>
                    <strong style={{ color: "#17213a" }}>{p.provider}</strong>
                    <div style={{ color: "#8b95a5", fontSize: 11 }}>{p.model}</div>
                  </td>
                  <td style={tdStyle}>{p.tenant_id || "platform"}</td>
                  <td style={tdStyle}>{p.requests || 0}</td>
                  <td style={tdStyle}>{p.failures || 0}</td>
                  <td style={tdStyle}>{p.rate_limits || 0}</td>
                  <td style={tdStyle}>
                    {p.cooldown_until ? (
                      <span style={{ color: "#c74646", fontSize: 12 }}>{p.cooldown_until}</span>
                    ) : (
                      <span style={{ color: "#1aa76c", fontSize: 12 }}>—</span>
                    )}
                  </td>
                  <td style={tdStyle}>
                    <button onClick={() => recover(p)} style={ghostBtn}>Reset</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = { display: "block", width: "100%", marginTop: 6, padding: 10, borderRadius: 8, border: "1px solid #d7dce5", fontSize: 13, outline: "none" };
const primaryBtn: React.CSSProperties = { background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: "pointer" };
const ghostBtn: React.CSSProperties = { background: "#fff", color: "#17213a", border: "1px solid #e5e7eb", padding: "7px 14px", borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: "pointer" };
const thStyle: React.CSSProperties = { textAlign: "left", padding: "12px 16px", fontSize: 11, color: "#8b97a9", textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600, borderBottom: "1px solid #edf0f5" };
const tdStyle: React.CSSProperties = { padding: "13px 16px", color: "#4b5563", verticalAlign: "top" };
'''

TARGET.write_text(CONTENT, encoding="utf-8")
print(f"File saved: {TARGET.stat().st_size} bytes")
print(f"Location: {TARGET}")