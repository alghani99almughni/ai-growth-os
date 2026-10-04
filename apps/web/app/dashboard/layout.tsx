"use client";
import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Topbar from "../../components/Topbar";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [tenant, setTenant] = useState<any>(null);
  const [user, setUser] = useState<any>(null);
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
    const isSuperAdmin = role === "platform_admin" || role === "super_admin";

    const urlTenant =
      typeof window !== "undefined"
        ? new URLSearchParams(window.location.search).get("tenant") || ""
        : "";

    // Super admin without a tenant: bounce to /platform (except when already viewing one)
    if (isSuperAdmin && !urlTenant && typeof window !== "undefined" && window.location.pathname === "/dashboard") {
      window.location.href = "/platform/tenants";
      return;
    }

    // Which tenant are we loading?
    let tenantId = "";
    if (isSuperAdmin && urlTenant) {
      tenantId = urlTenant;
    } else {
      try {
        const raw = localStorage.getItem("ago_tenant");
        tenantId = raw ? JSON.parse(raw)?.id || "" : "";
      } catch {}
    }

    if (!tenantId) {
      window.location.href = isSuperAdmin ? "/platform/tenants" : "/login";
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
          window.location.href = isSuperAdmin ? "/platform/tenants" : "/login";
          return;
        }
        setTenant(t);
        // If Super Admin is viewing a tenant, render as tenant
        const effectiveRole = (isSuperAdmin && urlTenant) ? "tenant" : (role || "tenant");
        setUser({
          role: effectiveRole,
          name: isSuperAdmin ? "Super Admin" : (t.name || "Business admin"),
          isSuperAdminView: isSuperAdmin && !!urlTenant,
        });
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

  return (
    <div style={{ minHeight: "100vh", background: "#f5f7fb" }}>
      <Sidebar
        role={user.role}
        tenantName={tenant?.name || "Your business"}
        workspaceLabel={user.isSuperAdminView ? "Viewing as Super Admin" : "Business workspace"}
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

      <style jsx global>{`
        @media (max-width: 900px) {
          .ago-sidebar { transform: translateX(-100%); }
          .ago-sidebar[data-open="true"] { transform: translateX(0); }
          .ago-content { margin-left: 0 !important; }
          .ago-hamburger { display: flex !important; }
          .ago-mobile-close { display: flex !important; }
        }
      `}</style>
    </div>
  );
}