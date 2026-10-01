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
    const t = localStorage.getItem("ago_tenant");
    if (t) {
      try { setTenant(JSON.parse(t)); } catch {}
    }
    // Best-effort read of the logged-in user; if the key doesn't exist we
    // fall back to a generic display name.
    const token = localStorage.getItem("ago_access_token") || "";
    // decode JWT payload (no verification, client-side only)
    if (token && token.split(".").length === 3) {
      try {
        const payload = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
        setUser({ role: payload.role || "tenant", name: payload.name || "User" });
      } catch {}
    }
    setReady(true);
  }, []);

  function logout() {
    localStorage.removeItem("ago_access_token");
    localStorage.removeItem("ago_tenant");
    window.location.href = "/login";
  }

  const role = user?.role || "tenant";
  const isAdmin = role === "platform_admin" || role === "super_admin";
  const tenantName = tenant?.name || (isAdmin ? "Platform" : "Your business");
  const workspaceLabel = isAdmin ? "Platform workspace" : "Business workspace";
  const userName = user?.name || (isAdmin ? "Super Admin" : "Business admin");

  return (
    <div style={{ minHeight: "100vh", background: "#f5f7fb" }}>
      <Sidebar
        role={role}
        tenantName={tenantName}
        workspaceLabel={workspaceLabel}
        mobileOpen={mobileOpen}
        onClose={() => setMobileOpen(false)}
        onLogout={logout}
      />
      <div style={{ marginLeft: 248 }} className="ago-content">
        <Topbar
          userName={userName}
          role={role}
          onOpenSidebar={() => setMobileOpen(true)}
          onLogout={logout}
        />
        <main style={{ padding: "28px 30px 50px", maxWidth: 1550, margin: "auto" }}>
          {ready ? children : (
            <div style={{ padding: 80, textAlign: "center", color: "#75839a" }}>Loading…</div>
          )}
        </main>
      </div>

      <style jsx global>{`
        @media (max-width: 900px) {
          .ago-sidebar {
            transform: translateX(-100%);
          }
          .ago-sidebar[data-open="true"] {
            transform: translateX(0);
          }
          .ago-content {
            margin-left: 0 !important;
          }
          .ago-hamburger {
            display: flex !important;
          }
          .ago-mobile-close {
            display: flex !important;
          }
        }
      `}</style>
    </div>
  );
}