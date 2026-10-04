"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Channel = {
  provider: string;
  connected: boolean;
  status: string | null;
  connected_phone: string | null;
  display_name: string | null;
};

type ChannelsResponse = {
  openwa: Channel;
  meta: Channel;
  priority: "openwa" | "meta";
  active: "openwa" | "meta" | null;
};

const PROVIDER_META: Record<string, { label: string; blurb: string; icon: string }> = {
  openwa: { label: "OpenWA", blurb: "Self-hosted WhatsApp gateway (Baileys).", icon: "🟢" },
  meta: { label: "Meta Cloud API", blurb: "Official WhatsApp Business Cloud API.", icon: "🔵" },
};

function ChannelCard({
  provider, channel, isPriority, isActive, onToggle, busy,
}: {
  provider: "openwa" | "meta";
  channel: Channel;
  isPriority: boolean;
  isActive: boolean;
  onToggle: (next: boolean) => void;
  busy: boolean;
}) {
  const meta = PROVIDER_META[provider];
  const connected = channel?.connected;

  return (
    <article
      className="card"
      style={{
        padding: 18,
        background: "#fff",
        border: isActive ? "2px solid #5b4eea" : "1px solid #e8ecf3",
        position: "relative",
      }}
    >
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10, alignItems: "center" }}>
        <span className="badge badge-grey">{meta.icon} {meta.label}</span>
        {isPriority && <span className="badge badge-purple">priority</span>}
        {isActive && <span className="badge badge-blue">active now</span>}
        <span className={"badge " + (connected ? "badge-blue" : "badge-grey")}>
          {connected ? "connected" : "not connected"}
        </span>
      </div>

      <p style={{ margin: "0 0 12px", color: "#75839a", fontSize: 12 }}>{meta.blurb}</p>

      <div style={{ fontSize: 13, color: "#33415c", lineHeight: 1.7 }}>
        <div><span style={{ color: "#75839a" }}>Status: </span><strong>{channel?.status || "unknown"}</strong></div>
        <div><span style={{ color: "#75839a" }}>Phone: </span><strong>{channel?.connected_phone || "—"}</strong></div>
        <div><span style={{ color: "#75839a" }}>Display name: </span><strong>{channel?.display_name || "—"}</strong></div>
      </div>

      <div style={{ marginTop: 14, display: "flex", gap: 8, alignItems: "center" }}>
        <button
          onClick={() => onToggle(!channel.connected)}
          disabled={busy || (!channel.connected && !isPriority)}
          title={!channel.connected && !isPriority ? "Connect this channel first" : undefined}
          style={{
            background: connected ? "#fff" : "#1a5c43",
            color: connected ? "#b6341f" : "#fff",
            border: connected ? "1px solid #f0c6c6" : 0,
            padding: "10px 16px",
            borderRadius: 10,
            fontWeight: 700,
            fontSize: 12,
            cursor: busy ? "wait" : "pointer",
            opacity: busy ? 0.6 : 1,
          }}
        >
          {busy ? "…" : connected ? "Turn off" : "Turn on"}
        </button>
        {connected && <span style={{ fontSize: 11, color: "#1d9c68", fontWeight: 600 }}>● on</span>}
        {!connected && <span style={{ fontSize: 11, color: "#8b95a5", fontWeight: 600 }}>○ off</span>}
      </div>
    </article>
  );
}

export default function WhatsappPanel({ tenantId, token }: { tenantId: string; token: string }) {
  const [data, setData] = useState<ChannelsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string>("");
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");

  const authHeaders = () => ({ Authorization: "Bearer " + token });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const res = await jget(`/api/v1/tenants/${tenantId}/integrations/whatsapp`);
      setData(res);
    } catch (e: any) {
      setError(e.message || "Could not load WhatsApp channels");
    }
    setLoading(false);
  }

  useEffect(() => {
    if (tenantId) void loadAll();
  }, [tenantId]);

  async function toggleChannel(provider: "openwa" | "meta", nextOn: boolean) {
    setBusyProvider(provider);
    setStatus("");
    setError("");
    try {
      const endpoint = nextOn ? "enable" : "disable";
      const r = await fetch(`${api()}/api/v1/tenants/${tenantId}/integrations/whatsapp/${provider}/${endpoint}`, {
        method: "POST",
        headers: authHeaders(),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Toggle failed");
      setStatus(`${PROVIDER_META[provider].label} ${nextOn ? "turned on" : "turned off"}.`);
      await loadAll();
    } catch (e: any) {
      setError(e.message || "Toggle failed");
    }
    setBusyProvider("");
  }

  return (
    <section className="card">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 style={{ margin: 0 }}>📱 WhatsApp channels</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            {data?.active
              ? `Currently sending via ${PROVIDER_META[data.active]?.label}.`
              : "No channel is currently active — messages will not be sent."}
          </p>
        </div>
        <button className="btn-ghost" onClick={loadAll} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>}
      {status && <p style={{ color: "#1aa76c", marginTop: 12, fontSize: 12 }}>{status}</p>}

      {!loading && data && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginTop: 20 }}>
            <ChannelCard
              provider="openwa"
              channel={data.openwa}
              isPriority={data.priority === "openwa"}
              isActive={data.active === "openwa"}
              onToggle={(next) => toggleChannel("openwa", next)}
              busy={busyProvider === "openwa"}
            />
            <ChannelCard
              provider="meta"
              channel={data.meta}
              isPriority={data.priority === "meta"}
              isActive={data.active === "meta"}
              onToggle={(next) => toggleChannel("meta", next)}
              busy={busyProvider === "meta"}
            />
          </div>

          <div style={{ marginTop: 20, padding: 14, background: "#f9fafc", border: "1px solid #e8ecf3", borderRadius: 10, fontSize: 13, color: "#33415c", lineHeight: 1.7 }}>
            <strong style={{ color: "#17213a" }}>Routing</strong>
            <div><span style={{ color: "#75839a" }}>Priority channel: </span><strong>{PROVIDER_META[data.priority]?.label}</strong></div>
            <div><span style={{ color: "#75839a" }}>Active now: </span><strong>{data.active ? PROVIDER_META[data.active]?.label : "— none —"}</strong></div>
            <p style={{ margin: "8px 0 0", fontSize: 12, color: "#75839a" }}>
              Use <b>Turn off</b> to pause a channel without removing its credentials. <b>Turn on</b> resumes it.
            </p>
          </div>
        </>
      )}
    </section>
  );
}