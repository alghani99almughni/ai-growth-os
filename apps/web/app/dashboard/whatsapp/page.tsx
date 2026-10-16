"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import WhatsAppInboxPanel from "../../../components/WhatsAppInboxPanel";
import WhatsAppConnectForm from "../../../components/WhatsAppConnectForm";

export default function WhatsappPage() {
  const searchParams = useSearchParams();
  const [tenantId, setTenantId] = useState("");
  const [token, setToken] = useState("");

  useEffect(() => {
    const urlTenant = searchParams?.get("tenant") || "";
    if (urlTenant) {
      setTenantId(urlTenant);
    } else {
      try {
        const raw = localStorage.getItem("ago_tenant");
        const t = raw ? JSON.parse(raw) : null;
        if (t?.id) setTenantId(t.id);
      } catch {}
    }
    setToken(localStorage.getItem("ago_access_token") || "");
  }, [searchParams]);

  if (!tenantId || !token) {
    return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
          WhatsApp
        </h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Connected channels, chats, and replies.
        </p>
      </div>

      <WhatsAppConnectForm tenantId={tenantId} token={token} />
      <WhatsAppInboxPanel tenantId={tenantId} token={token} />
    </div>
  );
}