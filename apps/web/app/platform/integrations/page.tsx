"use client";

import { useState } from "react";
import PlatformEmailPage from "../email/page";

type Tab = "whatsapp" | "email";

export default function PlatformIntegrationsPage() {
  const [tab, setTab] = useState<Tab>("whatsapp");

  return (
    <div>
      <header style={{ marginBottom: 22 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
          Tenant integrations
        </h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Manage tenant communication channels from one Super Admin workspace.
        </p>
      </header>

      <nav aria-label="Integration type" style={{ display: "flex", gap: 8, borderBottom: "1px solid #e3e8f0", marginBottom: 22 }}>
        <button
          type="button"
          onClick={() => setTab("whatsapp")}
          aria-pressed={tab === "whatsapp"}
          style={tabButton(tab === "whatsapp")}
        >
          WhatsApp
        </button>
        <button
          type="button"
          onClick={() => setTab("email")}
          aria-pressed={tab === "email"}
          style={tabButton(tab === "email")}
        >
          Email
        </button>
      </nav>

      {tab === "email" ? (
        <PlatformEmailPage />
      ) : (
        <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, maxWidth: 850 }}>
          <h2 style={{ margin: "0 0 8px", color: "#17213a", fontSize: 18 }}>WhatsApp tenant configuration</h2>
          <p style={{ margin: "0 0 12px", color: "#536174", fontSize: 13, lineHeight: 1.65 }}>
            The tenant WhatsApp settings currently use the tenant-scoped integrations API. The existing Super Admin WhatsApp route was found to be a duplicate of the Email dashboard and calls Email endpoints; it is not a working platform-wide WhatsApp manager.
          </p>
          <p style={{ margin: 0, color: "#536174", fontSize: 13, lineHeight: 1.65 }}>
            I have not exposed tenant credentials through a guessed endpoint. The next backend change must add a platform-admin, tenant-scoped WhatsApp overview/configuration API before this tab can safely save or change credentials.
          </p>
        </section>
      )}
    </div>
  );
}

function tabButton(active: boolean): React.CSSProperties {
  return {
    appearance: "none",
    border: 0,
    borderBottom: active ? "2px solid #1a5c43" : "2px solid transparent",
    background: "transparent",
    color: active ? "#1a5c43" : "#75839a",
    padding: "11px 15px",
    marginBottom: -1,
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
  };
}
