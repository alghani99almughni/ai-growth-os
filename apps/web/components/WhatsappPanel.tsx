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
  openwa: {
    label: "OpenWA",
    blurb: "Self-hosted WhatsApp gateway (Baileys).",
    icon: "🟢",
  },
  meta: {
    label: "Meta Cloud API",
    blurb: "Official WhatsApp Business Cloud API.",
    icon: "🔵",
  },
};

function ChannelCard({
  provider,
  channel,
  isPriority,
  isActive,
}: {
  provider: "openwa" | "meta";
  channel: Channel;
  isPriority: boolean;
  isActive: boolean;
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
      {/* Badges row */}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
        <span className="badge badge-grey">{meta.icon} {meta.label}</span>
        {isPriority && <span className="badge badge-purple">priority</span>}
        {isActive && <span className="badge badge-blue">active now</span>}
        <span className={"badge " + (connected ? "badge-blue" : "badge-grey")}>
          {connected ? "connected" : "not connected"}
        </span>
      </div>

      <p style={{ margin: "0 0 12px", color: "#75839a", fontSize: 12 }}>{meta.blurb}</p>

      {/* Details */}
      <div style={{ fontSize: 13, color: "#33415c", lineHeight: 1.7 }}>
        <div>
          <span style={{ color: "#75839a" }}>Status: </span>
          <strong>{channel?.status || "unknown"}</strong>
        </div>
        <div>
          <span style={{ color: "#75839a" }}>Phone: </span>
          <strong>{channel?.connected_phone || "—"}</strong>
        </div>
        <div>
          <span style={{ color: "#75839a" }}>Display name: </span>
          <strong>{channel?.display_name || "—"}</strong>
        </div>
      </div>
    </article>
  );
}

export default function WhatsappPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [data, setData] = useState<ChannelsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  return (
    <section className="card">
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
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

      {!loading && data && (
        <>
          {/* Two channel cards */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 14,
              marginTop: 20,
            }}
          >
            <ChannelCard
              provider="openwa"
              channel={data.openwa}
              isPriority={data.priority === "openwa"}
              isActive={data.active === "openwa"}
            />
            <ChannelCard
              provider="meta"
              channel={data.meta}
              isPriority={data.priority === "meta"}
              isActive={data.active === "meta"}
            />
          </div>

          {/* Routing summary */}
          <div
            style={{
              marginTop: 20,
              padding: 14,
              background: "#f9fafc",
              border: "1px solid #e8ecf3",
              borderRadius: 10,
              fontSize: 13,
              color: "#33415c",
              lineHeight: 1.7,
            }}
          >
            <strong style={{ color: "#17213a" }}>Routing</strong>
            <div>
              <span style={{ color: "#75839a" }}>Priority channel: </span>
              <strong>{PROVIDER_META[data.priority]?.label}</strong>
            </div>
            <div>
              <span style={{ color: "#75839a" }}>Active now: </span>
              <strong>
                {data.active ? PROVIDER_META[data.active]?.label : "— none —"}
              </strong>
            </div>
            <p style={{ margin: "8px 0 0", fontSize: 12, color: "#75839a" }}>
              Outbound messages go through the priority channel. If it is not
              connected, the other channel takes over automatically when available.
            </p>
          </div>
        </>
      )}

      {!loading && !data && !error && (
        <div className="empty-state" style={{ marginTop: 20 }}>
          <h3>No channel data</h3>
          <p>The API returned an empty response.</p>
        </div>
      )}

      {/* Placeholder for v2 */}
      <p
        style={{
          marginTop: 20,
          fontSize: 12,
          color: "#98a2b4",
        }}
      >
        Configure channels, change priority, and disconnect — coming in v2.
      </p>
    </section>
  );
}