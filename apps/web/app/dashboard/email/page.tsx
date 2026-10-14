"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import EmailPanel from "../../../components/EmailPanel";

export default function EmailPage() {
  const searchParams = useSearchParams();
  const [tenantId, setTenantId] = useState<string>("");
  const [token, setToken] = useState<string>("");

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
    return (
      <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>
        Loading…
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
          Email
        </h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Connect business mailboxes, review conversations, and reply inline.
        </p>
      </div>
      <EmailPanel tenantId={tenantId} token={token} />
    </div>
  );
}