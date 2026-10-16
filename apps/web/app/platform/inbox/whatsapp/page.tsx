"use client";
import { useEffect, useState } from "react";
import WhatsAppInboxPanel from "../../../../components/WhatsAppInboxPanel";
import WhatsAppConnectForm from "../../../../components/WhatsAppConnectForm";

const api = () =>
  String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export default function PlatformWhatsAppInboxPage() {
  const [tenantId, setTenantId] = useState("");
  const [token, setToken] = useState("");

  useEffect(() => {
    const tok = localStorage.getItem("ago_access_token") || "";
    setToken(tok);
    if (!tok) return;
    fetch(api() + "/api/v1/auth/me", {
      headers: { Authorization: "Bearer " + tok }, cache: "no-store",
    })
      .then((r) => r.json())
      .then((d) => { if (d?.tenant?.id) setTenantId(d.tenant.id); });
  }, []);

  if (!tenantId || !token) {
    return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
          WhatsApp Inbox
        </h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Your platform WhatsApp — chats and replies.
        </p>
      </div>

      <WhatsAppConnectForm tenantId={tenantId} token={token} />
      <WhatsAppInboxPanel tenantId={tenantId} token={token} />
    </div>
  );
}