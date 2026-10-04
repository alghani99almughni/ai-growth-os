"use client";
import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Topbar from "../../components/Topbar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<any>(null);
  const [tenant, setTenant] = useState<any>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) {
      window.location.href = "/login";
      return;
    }
    let role = "";
    if (token.split(".").length === 3) {
      try {
        const p = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
        role = p.role || "";
      } catch {}
    }
    const isAdmin = role === "platform_admin" || role === "super_admin";

    const urlTenant = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("tenant") || ""
      : "";

    // Super Admin must supply a tenant
    if (isAdmin && !urlTenant) {
      // If on /dashboard root, bounce to /platform/tenants
      if (typeof window !== "undefined" && window.location.pathname === "/dashboard") {
        window.location.href = "/platform/tenants";
        return;
      }
    }

    const tenantId = isAdmin ? urlTenant : (() => {
      try { return JSON.parse(localStorage.getItem("ago_tenant") || "null")?.id || ""; } catch { return ""; }
    })();

    if (!tenantId) {
      window.location.href = "/login";
      return;
    }

    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${api}/api/v1/tenants/${tenantId}`, {
      headers: { Authorization: "Bearer " + token },
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((t) => {
        if (!t) {
          window.location.href = isAdmin ? "/platform/tenants" : "/login";
          return;
        }
        setTenant(t);
        setUser({ role, name: isAdmin ? "Super Admin" : (t.name || "Business admin") });
        setReady(true);
      })
      .catch(() => {
        window.location.href = "/login";
      });
  }, []);

  function logout() {
    localStorage.removeItem("ago_access_token");
    localStorage.removeItem("ago_tenant");
    window.location.href = "/login";
  }

  if (!ready || !user) {
    return <div style={{ padding: 80, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  }

  const isAdmin = user.role === "platform_admin" || user.role === "super_admin";

  return (
    <div style={{ minHeight: "100vh", background: "#f5f7fb" }}>
      <Sidebar
        role={isAdmin ? "platform_admin" : "tenant"}
        tenantName={tenant?.name || "Your business"}
        workspaceLabel={isAdmin ? "Viewing as Super Admin" : "Business workspace"}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        onLogout={logout}
      />
      <div style={{ marginLeft: 248 }} className="ago-content">
        <Topbar
          userName={user.name}
          role={user.role}
          onOpenSidebar={() => setMobileOpen(true)}
          onLogout={logout}
        />
        <main style={{ padding: "28px 30px 50px", maxWidth: 1550, margin: "auto" }}>
          {children}
        </main>
      </div>
    </div>
  );
}