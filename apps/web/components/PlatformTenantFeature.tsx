"use client";

import { useEffect, useState } from "react";
import CallsPanel from "./CallsPanel";
import BookingsPanel from "./BookingsPanel";
import OrdersPanel from "./OrdersPanel";
import CrmPanel from "./CrmPanel";
import ServicesPanel from "./ServicesPanel";
import TeamPanel from "./TeamPanel";

type Feature = "calls" | "bookings" | "orders" | "customers" | "services" | "team";
type Tenant = { id: string; name: string; slug?: string; industry?: string; status?: string };

const API = () => process.env.NEXT_PUBLIC_API_URL || "https://ai-growth-os-api.onrender.com";
const TITLES: Record<Feature, string> = {
  calls: "Calls & Transcripts",
  bookings: "Bookings",
  orders: "Orders",
  customers: "Customers / CRM",
  services: "Services",
  team: "Team",
};

export default function PlatformTenantFeature({ feature }: { feature: Feature }) {
  const [token, setToken] = useState("");
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const access = localStorage.getItem("ago_access_token") || "";
    setToken(access);
    const requestedTenant = new URLSearchParams(window.location.search).get("tenant") || "";
    if (!access) {
      setError("Your session has expired. Please sign in again.");
      setLoading(false);
      return;
    }
    fetch(API() + "/api/v1/platform/tenants", {
      headers: { Authorization: "Bearer " + access },
      cache: "no-store",
    })
      .then(async (r) => {
        const body = await r.json();
        if (!r.ok) throw new Error(body.detail || "Unable to load tenants");
        const list: Tenant[] = body.items || [];
        setTenants(list);
        const initial = list.some((t) => t.id === requestedTenant)
          ? requestedTenant
          : (list[0]?.id || "");
        setTenantId(initial);
        setLoading(false);
      })
      .catch((e) => {
        setError(e?.message || "Unable to load tenants");
        setLoading(false);
      });
  }, []);

  const panelProps = { tenantId, token };
  return (
    <main style={{ padding: "28px 30px", maxWidth: 1440, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 20, flexWrap: "wrap", marginBottom: 22 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: ".12em", color: "#5b5cf0", marginBottom: 8 }}>SUPER ADMIN · TENANT OPERATIONS</div>
          <h1 style={{ margin: 0, fontSize: 27, letterSpacing: "-.03em", color: "#17213a" }}>{TITLES[feature]}</h1>
          <p style={{ margin: "7px 0 0", color: "#75839a", fontSize: 13 }}>Use the existing tenant feature to inspect and manage one selected tenant. Tenant-side access remains unchanged.</p>
        </div>
        <label style={{ display: "grid", gap: 7, minWidth: 270, color: "#4b5563", fontSize: 12, fontWeight: 700 }}>
          Select tenant
          <select value={tenantId} onChange={(e) => { setTenantId(e.target.value); const u = new URL(window.location.href); u.searchParams.set("tenant", e.target.value); window.history.replaceState({}, "", u.toString()); }} disabled={loading || tenants.length === 0} style={{ padding: "11px 13px", border: "1px solid #d7dce5", borderRadius: 10, background: "#fff", color: "#17213a", minWidth: 270 }}>
            {tenants.length === 0 && <option value="">No tenants available</option>}
            {tenants.map((t) => <option key={t.id} value={t.id}>{t.name}{t.industry ? " · " + t.industry : ""}</option>)}
          </select>
        </label>
      </div>
      {loading && <p style={{ color: "#75839a" }}>Loading tenant list…</p>}
      {error && <div role="alert" style={{ padding: 14, borderRadius: 10, background: "#fff1f1", color: "#b42318", marginBottom: 16 }}>{error}</div>}
      {!loading && !error && tenants.length === 0 && <p>No tenants were returned by the platform API.</p>}
      {!loading && !error && tenantId && token && (
        <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18 }}>
          {feature === "calls" && <CallsPanel {...panelProps} />}
          {feature === "bookings" && <BookingsPanel {...panelProps} />}
          {feature === "orders" && <OrdersPanel {...panelProps} />}
          {feature === "customers" && <CrmPanel {...panelProps} />}
          {feature === "services" && <ServicesPanel {...panelProps} />}
          {feature === "team" && <TeamPanel {...panelProps} />}
        </section>
      )}
    </main>
  );
}
