"use client";
import { useEffect, useState } from "react";
import EmailInboxPanel from "./EmailInboxPanel";
import AddMailboxModal from "./AddMailboxModal";

const api = () =>
  String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export default function PlatformInboxPage() {
  const [tenantId, setTenantId] = useState("");
  const [token, setToken] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [accountCount, setAccountCount] = useState<number | null>(null);

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

  async function refreshAccounts() {
    if (!tenantId || !token) return;
    const r = await fetch(api() + `/api/v1/tenants/${tenantId}/email-accounts`, {
      headers: { Authorization: "Bearer " + token }, cache: "no-store",
    });
    const x = await r.json().catch(() => ({ items: [] }));
    setAccountCount((x.items || []).length);
  }

  useEffect(() => { void refreshAccounts(); }, [tenantId, token]);

  if (!tenantId || !token) {
    return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
            Inbox
          </h1>
          <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
            Your platform email — threads, replies, search.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 12, color: "#8490a4" }}>
            {accountCount === null ? "" : `${accountCount} mailbox${accountCount === 1 ? "" : "es"}`}
          </span>
          <button
            onClick={() => setShowAdd(true)}
            style={{
              padding: "10px 18px", border: 0,
              background: "linear-gradient(135deg,#5b5cf0,#7159f7)",
              color: "#fff", borderRadius: 10, fontSize: 13,
              fontWeight: 700, cursor: "pointer",
            }}
          >
            + Connect mailbox
          </button>
        </div>
      </div>

      <EmailInboxPanel tenantId={tenantId} token={token} />

      {showAdd && (
        <AddMailboxModal
          tenantId={tenantId}
          token={token}
          onClose={() => setShowAdd(false)}
          onDone={async () => {
            setShowAdd(false);
            await refreshAccounts();
          }}
        />
      )}
    </div>
  );
}