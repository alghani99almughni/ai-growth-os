"use client";
import { useEffect, useState } from "react";

const api = () =>
  String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type Channel = {
  provider: string;
  status: string;
  connected_phone?: string | null;
  display_name?: string | null;
};

export default function WhatsAppConnectForm({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [tab, setTab] = useState<"openwa" | "meta">("openwa");
  const [channels, setChannels] = useState<Record<string, Channel>>({});
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const [openwa, setOpenwa] = useState({ base_url: "", api_key: "", session_id: "" });
  const [meta, setMeta] = useState({ access_token: "", phone_number_id: "" });

  const h = { Authorization: "Bearer " + token, "Content-Type": "application/json" };

  async function loadChannels() {
    try {
      const r = await fetch(api() + `/api/v1/tenants/${tenantId}/integrations/whatsapp`, {
        headers: h, cache: "no-store",
      });
      const x = await r.json();
      setChannels(x || {});
    } catch {}
  }

  useEffect(() => { void loadChannels(); }, [tenantId]);

  async function saveOpenWA() {
    setBusy(true); setStatus("");
    try {
      const r = await fetch(api() + `/api/v1/tenants/${tenantId}/integrations/whatsapp/openwa`, {
        method: "PUT", headers: h, body: JSON.stringify(openwa),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "OpenWA connect failed");
      setStatus("OpenWA connected");
      await loadChannels();
    } catch (e: any) {
      setStatus(e.message);
    }
    setBusy(false);
  }

  async function saveMeta() {
    setBusy(true); setStatus("");
    try {
      const r = await fetch(api() + `/api/v1/tenants/${tenantId}/integrations/whatsapp/meta`, {
        method: "PUT", headers: h, body: JSON.stringify(meta),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Meta connect failed");
      setStatus("Meta connected");
      await loadChannels();
    } catch (e: any) {
      setStatus(e.message);
    }
    setBusy(false);
  }

  async function disconnect(provider: string) {
    if (!confirm(`Disconnect ${provider}?`)) return;
    await fetch(api() + `/api/v1/tenants/${tenantId}/integrations/whatsapp/${provider}`, {
      method: "DELETE", headers: h,
    });
    await loadChannels();
  }

  async function setPriority(provider: "openwa" | "meta") {
    await fetch(api() + `/api/v1/tenants/${tenantId}/integrations/whatsapp/priority`, {
      method: "PUT", headers: h, body: JSON.stringify({ priority: provider }),
    });
    await loadChannels();
  }

  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20, marginBottom: 20 }}>
      <h2 style={{ margin: 0, fontSize: 15, color: "#17213a" }}>WhatsApp channels</h2>
      <p style={{ margin: "4px 0 14px", color: "#75839a", fontSize: 12 }}>
        Connect one or both. Whichever has priority handles outbound messages.
      </p>

      {/* Connected channels summary */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        {["openwa", "meta"].map((p) => {
          const c = channels[p] || { status: "disconnected" };
          const connected = c.status === "connected";
          return (
            <div key={p} style={{
              padding: "8px 12px", border: "1px solid #e8ecf3", borderRadius: 10,
              fontSize: 12, display: "flex", gap: 8, alignItems: "center",
            }}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: connected ? "#1aa76c" : "#c0c7d1",
              }} />
              <strong>{p === "openwa" ? "OpenWA" : "Meta Cloud API"}</strong>
              <span style={{ color: "#75839a" }}>
                {connected ? (c.connected_phone || "connected") : "not connected"}
              </span>
              {connected && (
                <>
                  <button onClick={() => setPriority(p as "openwa" | "meta")}
                    style={{ background: "none", border: 0, color: "#5b5cf0", cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
                    Set priority
                  </button>
                  <button onClick={() => disconnect(p)}
                    style={{ background: "none", border: 0, color: "#b00", cursor: "pointer", fontSize: 11, fontWeight: 600 }}>
                    Disconnect
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 12, borderBottom: "1px solid #eef1f5" }}>
        {(["openwa", "meta"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              background: "none", border: 0, padding: "8px 14px",
              color: tab === t ? "#17213a" : "#75839a",
              fontWeight: tab === t ? 700 : 500,
              borderBottom: tab === t ? "2px solid #25D366" : "2px solid transparent",
              cursor: "pointer", fontSize: 13, marginBottom: -1,
            }}
          >
            {t === "openwa" ? "OpenWA" : "Meta Cloud API"}
          </button>
        ))}
      </div>

      {status && (
        <div style={{ fontSize: 12, color: status.toLowerCase().includes("connected") ? "#1aa76c" : "#b00", marginBottom: 12 }}>
          {status}
        </div>
      )}

      {tab === "openwa" && (
        <div style={{ display: "grid", gap: 12 }}>
          <label style={lbl}>Base URL
            <input value={openwa.base_url} onChange={(e) => setOpenwa({ ...openwa, base_url: e.target.value })}
              placeholder="https://openwa.yourhost.com" style={inp} />
          </label>
          <label style={lbl}>API key
            <input value={openwa.api_key} onChange={(e) => setOpenwa({ ...openwa, api_key: e.target.value })}
              placeholder="paste API key" style={inp} />
          </label>
          <label style={lbl}>Session ID
            <input value={openwa.session_id} onChange={(e) => setOpenwa({ ...openwa, session_id: e.target.value })}
              placeholder="session name" style={inp} />
          </label>
          <button onClick={saveOpenWA} disabled={busy || !openwa.base_url || !openwa.api_key || !openwa.session_id}
            style={{ ...btnPrimary, opacity: busy || !openwa.base_url || !openwa.api_key || !openwa.session_id ? 0.6 : 1 }}>
            {busy ? "Connecting…" : "Connect OpenWA"}
          </button>
        </div>
      )}

      {tab === "meta" && (
        <div style={{ display: "grid", gap: 12 }}>
          <label style={lbl}>Access token
            <input value={meta.access_token} onChange={(e) => setMeta({ ...meta, access_token: e.target.value })}
              placeholder="permanent system user token" style={inp} />
          </label>
          <label style={lbl}>Phone number ID
            <input value={meta.phone_number_id} onChange={(e) => setMeta({ ...meta, phone_number_id: e.target.value })}
              placeholder="e.g. 123456789012345" style={inp} />
          </label>
          <p style={{ fontSize: 11, color: "#75839a", margin: 0 }}>
            Get these from Meta Business Suite → WhatsApp → API Setup.
          </p>
          <button onClick={saveMeta} disabled={busy || !meta.access_token || !meta.phone_number_id}
            style={{ ...btnPrimary, opacity: busy || !meta.access_token || !meta.phone_number_id ? 0.6 : 1 }}>
            {busy ? "Connecting…" : "Connect Meta"}
          </button>
        </div>
      )}
    </div>
  );
}

const lbl: React.CSSProperties = { display: "block", fontSize: 12, color: "#4b5563", fontWeight: 600 };
const inp: React.CSSProperties = {
  display: "block", width: "100%", marginTop: 6, padding: 10, borderRadius: 8,
  border: "1px solid #d7dce5", fontSize: 13, outline: "none", boxSizing: "border-box",
};
const btnPrimary: React.CSSProperties = {
  padding: "11px 20px", border: 0, background: "linear-gradient(135deg,#25D366,#128C7E)",
  color: "#fff", borderRadius: 10, fontSize: 13, fontWeight: 700, cursor: "pointer",
  justifySelf: "start",
};