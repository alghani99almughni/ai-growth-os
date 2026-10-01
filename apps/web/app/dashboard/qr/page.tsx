"use client";
import { useEffect, useState } from "react";
import QrPanel from "../../../components/QrPanel";

export default function QrPage() {
  const [tenantId, setTenantId] = useState<string>("");
  const [token, setToken] = useState<string>("");

  useEffect(() => {
    const raw = localStorage.getItem("ago_tenant");
    let t: any = null;
    try { t = raw ? JSON.parse(raw) : null; } catch {}
    if (t?.id) setTenantId(t.id);
    setToken(localStorage.getItem("ago_access_token") || "");
  }, []);

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
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>QR codes</h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Generate and track Business, Context, and Campaign QR codes.
        </p>
      </div>
      <QrPanel tenantId={tenantId} token={token} />
    </div>
  );
}