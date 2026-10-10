"use client";
import { useEffect, useState } from "react";
import { Phone, ClipboardList, Users, Sparkles, CalendarDays } from "lucide-react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Overview() {
  const [tenant, setTenant] = useState<any>(null);
  const [redirecting, setRedirecting] = useState(false);
  const [viewingTenantId, setViewingTenantId] = useState<string>("");

  const [callsWaiting, setCallsWaiting] = useState<number>(0);
  const [openOrders, setOpenOrders] = useState<number>(0);
  const [openLeads, setOpenLeads] = useState<number>(0);
  const [customers, setCustomers] = useState<number>(0);
  const [bookingsToday, setBookingsToday] = useState<number>(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    let role = "";
    if (token.split(".").length === 3) {
      try {
        const p = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
        role = p.role || "";
      } catch {}
    }
    const isSuperAdmin = role === "platform_admin" || role === "super_admin";

    const urlTenant =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("tenant") || ""
        : "";

    // Super Admin with a tenant param → load that tenant. Without → bounce to platform list.
    if (isSuperAdmin) {
      if (!urlTenant) {
        setRedirecting(true);
        window.location.href = "/platform/tenants";
        return;
      }
      setViewingTenantId(urlTenant);
      fetch(`${api()}/api/v1/tenants/${urlTenant}`, {
        headers: { Authorization: "Bearer " + token },
        cache: "no-store",
      })
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          if (data) setTenant(data);
          else setRedirecting(true);
        })
        .catch(() => setRedirecting(true));
      return;
    }

    // Normal tenant path
    let t: any = null;
    try {
      const raw = localStorage.getItem("ago_tenant");
      t = raw ? JSON.parse(raw) : null;
    } catch {}
    if (!t?.id) {
      window.location.href = "/onboarding";
      return;
    }
    setViewingTenantId(t.id);
    setTenant(t);
  }, []);

  useEffect(() => {
    if (!viewingTenantId) return;
    const token = localStorage.getItem("ago_access_token") || "";
    const h = { Authorization: "Bearer " + token };

    async function jget(path: string) {
      try {
        const res = await fetch(api() + path, { headers: h, cache: "no-store" });
        if (!res.ok) return null;
        return await res.json();
      } catch {
        return null;
      }
    }

    (async () => {
      setLoading(true);
      const [calls, orders, leads, custs, appts] = await Promise.all([
        jget(`/api/v1/tenants/${viewingTenantId}/call-logs?limit=200`),
        jget(`/api/v1/tenants/${viewingTenantId}/orders`),
        jget(`/api/v1/tenants/${viewingTenantId}/leads`),
        jget(`/api/v1/tenants/${viewingTenantId}/customers`),
        jget(`/api/v1/tenants/${viewingTenantId}/appointments`),
      ]);

      setCallsWaiting((calls?.items || []).filter((c: any) => c.status === "waiting" || c.status === "ringing").length);
      setOpenOrders((orders?.items || []).filter((o: any) => ["confirmed", "preparing", "ready"].includes(o.status)).length);
      setOpenLeads((leads?.items || []).filter((l: any) => ["new", "qualified", "routed"].includes(l.status)).length);
      setCustomers((custs?.items || []).length);
      const today = new Date().toISOString().slice(0, 10);
      setBookingsToday((appts?.items || []).filter((a: any) => (a.starts_at || a.date || "").startsWith(today)).length);

      setLoading(false);
    })();
  }, [viewingTenantId]);

  if (redirecting) {
    return <div style={{ padding: 80, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  }
  if (!tenant) {
    return <div style={{ padding: 80, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  }

  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
          {greeting}, {tenant.name}
        </h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Here's what's happening today.
        </p>
        <a href={"/dashboard/industry" + (viewingTenantId ? "?tenant=" + viewingTenantId : "")} style={{ display: "inline-block", marginTop: 12, padding: "9px 12px", borderRadius: 9, background: "#efefff", color: "#5553d8", fontWeight: 700, fontSize: 12, textDecoration: "none" }}>Industry & business type settings →</a>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14, marginBottom: 24 }}>
        <KpiCard icon={<Phone size={18} />} label="Calls waiting" value={callsWaiting} color="#4d6df3" bg="#eaf0ff" loading={loading} />
        <KpiCard icon={<ClipboardList size={18} />} label="Open orders" value={openOrders} color="#e99132" bg="#fff0df" loading={loading} />
        <KpiCard icon={<Sparkles size={18} />} label="Open leads" value={openLeads} color="#8a62ed" bg="#f1ebff" loading={loading} />
        <KpiCard icon={<Users size={18} />} label="Customers" value={customers} color="#20aa72" bg="#e5f9f0" loading={loading} />
        <KpiCard icon={<CalendarDays size={18} />} label="Bookings today" value={bookingsToday} color="#20a7a0" bg="#e5f8f8" loading={loading} />
      </div>

      <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 24 }}>
        <h2 style={{ margin: 0, fontSize: 15, color: "#17213a" }}>Get started</h2>
        <p style={{ margin: "6px 0 16px", color: "#75839a", fontSize: 13 }}>
          Use the sidebar to manage calls, orders, bookings, QR codes, and more.
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <a href="/dashboard/qr" style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", padding: "11px 18px", borderRadius: 10, fontSize: 13, fontWeight: 700, textDecoration: "none" }}>
            Generate your QR
          </a>
          <a href="/dashboard/calls" style={{ background: "#fff", color: "#17213a", border: "1px solid #e5e7eb", padding: "11px 18px", borderRadius: 10, fontSize: 13, fontWeight: 600, textDecoration: "none" }}>
            View live calls
          </a>
        </div>
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, color, bg, loading }: { icon: React.ReactNode; label: string; value: number; color: string; bg: string; loading: boolean }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 20, boxShadow: "0 4px 18px rgba(34,52,91,0.04)" }}>
      <div style={{ width: 37, height: 37, borderRadius: 10, display: "grid", placeItems: "center", color, background: bg, marginBottom: 14 }}>
        {icon}
      </div>
      <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: "#17213a", marginTop: 6 }}>
        {loading ? "…" : value}
      </div>
    </div>
  );
}