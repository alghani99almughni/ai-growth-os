"use client";
import { useEffect, useState } from "react";
import EmailInboxPanel from "./EmailInboxPanel";

export default function PlatformInboxPage() {
  const [tenantId, setTenantId] = useState("");
  const [token, setToken] = useState("");

  useEffect(() => {
    const tok = localStorage.getItem("ago_access_token") || "";
    setToken(tok);
    if (!tok) return;
    fetch(
      (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "") +
        "/api/v1/auth/me",
      { headers: { Authorization: "Bearer " + tok }, cache: "no-store" }
    )
      .then((r) => r.json())
      .then((d) => {
        if (d?.tenant?.id) setTenantId(d.tenant.id);
      });
  }, []);

  if (!tenantId || !token) {
    return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  }

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
          Inbox
        </h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Your platform email — threads, replies, search.
        </p>
      </div>
      <EmailInboxPanel tenantId={tenantId} token={token} />
    </div>
  );
}