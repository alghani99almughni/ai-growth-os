"use client";
import { useEffect, useState } from "react";
import Sidebar from "../../components/Sidebar";
import Topbar from "../../components/Topbar";

export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<any>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("ago_access_token") || "";
    if (!token) {
      window.location.href = "/login";
      return;
    }
    // Decode JWT payload (client-side, no verification)
    if (token.split(".").length === 3) {
      try {
        const payload = JSON.parse(
          atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))
        );
        // Verify role — only platform admins belong here
        if (payload.role !== "platform_admin" && payload.role !== "super_admin") {
          window.location.href = "/dashboard";
          return;
        }
        setUser({
          role: payload.role,
          name: payload.name || "Super Admin",
        });
      } catch {
        window.location.href = "/login";
        return;
      }
    }
    setReady(true);
  }, []);

  function logout() {
    localStorage.removeItem("ago_access_token");
    localStorage.removeItem("ago_tenant");
    window.location.href = "/login";
  }

  if (!ready || !user) {
    return (
      <div style={{ padding: 80, textAlign: "center", color: "#75839a" }}>
        Loading…
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "#f5f7fb" }}>
      <Sidebar
        role={user.role}
        tenantName="Platform"
        workspaceLabel="Platform workspace"
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