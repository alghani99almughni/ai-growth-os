"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  Bot,
  Brain,
  Building2,
  CalendarDays,
  ClipboardList,
  FileText,
  Gift,
  Globe,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  MessageCircle,
  Mail,
  MessageSquare,
  Phone,
  QrCode,
  Settings2,
  ShoppingBag,
  Sparkles,
  Star,
  ToggleLeft,
  UserCog,
  Users,
  X,
} from "lucide-react";
import { TENANT_NAV, ADMIN_NAV, type NavItem } from "../lib/nav";
import { LANGUAGES, useTranslation, setLang } from "../lib/i18n";

const ICONS: Record<string, any> = {
  Activity,
  AlertTriangle,
  Bot,
  Brain,
  Building2,
  CalendarDays,
  ClipboardList,
  FileText,
  Gift,
  Globe,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  MessageCircle,
  Mail,
  MessageSquare,
  Phone,
  QrCode,
  Settings2,
  ShoppingBag,
  Sparkles,
  Star,
  ToggleLeft,
  UserCog,
  Users,
  X,
};

function Icon({ name, size = 18 }: { name: string; size?: number }) {
  const C = ICONS[name] || Sparkles;
  return <C size={size} />;
}

export default function Sidebar({
  role,
  tenantName,
  workspaceLabel,
  mobileOpen,
  onClose,
  onLogout,
}: {
  role: "platform_admin" | "tenant" | string;
  tenantName: string;
  workspaceLabel: string;
  mobileOpen: boolean;
  onClose: () => void;
  onLogout: () => void;
}) {
  const pathname = usePathname() || "";
  const { t } = useTranslation();
  const isAdmin = role === "platform_admin" || role === "super_admin";
  const items: NavItem[] = isAdmin ? ADMIN_NAV : TENANT_NAV;
  
  const isActive = (item: NavItem) => {
    if (item.exact) return pathname === item.href;
    return pathname === item.href || pathname.startsWith(item.href + "/");
  };
    const tenantParam = (() => {
    if (typeof window === "undefined") return "";
    const t = new URLSearchParams(window.location.search).get("tenant");
    return t ? `?tenant=${encodeURIComponent(t)}` : "";
  })();

  return (
    <>
      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(7,21,46,0.5)",
            backdropFilter: "blur(4px)",
            zIndex: 40,
          }}
        />
      )}

      <aside
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          bottom: 0,
          width: 248,
          background: "linear-gradient(180deg, #07172e 0%, #0a1d37 65%, #07162b 100%)",
          color: "#dce6f8",
          display: "flex",
          flexDirection: "column",
          zIndex: 50,
          transform: mobileOpen ? "translateX(0)" : undefined,
          transition: "transform 0.2s ease",
        }}
        className="ago-sidebar"
      >
        {/* Brand */}
        <div style={{ padding: "22px 18px 12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, justifyContent: "space-between" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 15, color: "#fff", fontWeight: 700 }}>
              <div
                style={{
                  width: 30,
                  height: 30,
                  borderRadius: 10,
                  background: "linear-gradient(135deg, #6d5dfc, #20b6a7)",
                  display: "grid",
                  placeItems: "center",
                  boxShadow: "0 8px 20px rgba(78,80,213,0.27)",
                }}
              >
                <Sparkles size={16} />
              </div>
              AI Growth OS
            </div>
            <button
              onClick={onClose}
              className="ago-mobile-close"
              style={{ background: "transparent", color: "#dce6f8", padding: 6, display: "none" }}
            >
              <X size={18} />
            </button>
          </div>

          {/* Workspace */}
          <div
            style={{
              marginTop: 22,
              padding: 12,
              background: "rgba(255,255,255,0.045)",
              border: "1px solid rgba(255,255,255,0.06)",
              borderRadius: 13,
              display: "flex",
              alignItems: "center",
              gap: 9,
            }}
          >
            <div
              style={{
                width: 31,
                height: 31,
                borderRadius: "50%",
                display: "grid",
                placeItems: "center",
                background: "#e8edf8",
                color: "#21355d",
                fontWeight: 800,
                fontSize: 11,
              }}
            >
              {isAdmin ? "SS" : (tenantName || "?").slice(0, 2).toUpperCase()}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 12,
                  color: "#fff",
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {isAdmin ? "Super Admin" : (tenantName || "Your business")}
              </div>
              <div style={{ fontSize: 10, color: "#91a4c1", marginTop: 3 }}>{workspaceLabel}</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <div
          style={{
            padding: "16px 20px 8px",
            color: "#7186a6",
            fontSize: 10,
            fontWeight: 800,
            letterSpacing: "0.12em",
          }}
        >
          {isAdmin ? "PLATFORM" : "BUSINESS"}
        </div>

        <nav style={{ padding: "0 10px", overflowY: "auto", flex: 1 }}>
          {items.map((item) => {
            const active = isActive(item);
            return (
              <Link
                key={item.href}
                href={item.href + tenantParam}
                onClick={onClose}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "10px 12px",
                  borderRadius: 9,
                  textAlign: "left",
                  fontSize: 12,
                  margin: "2px 0",
                  color: active ? "#fff" : "#aebed6",
                  background: active
                    ? "linear-gradient(90deg, #5b4eea, #6b5cf5)"
                    : "transparent",
                  boxShadow: active ? "0 7px 18px rgba(61,53,160,0.27)" : "none",
                  textDecoration: "none",
                  transition: "background 0.12s",
                }}
              >
                <Icon name={item.icon} size={17} />
                <span>{item.labelKey ? t(item.labelKey) : item.label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div style={{ padding: 14 }}>
          {!isAdmin && (
            <div
              style={{
                marginBottom: 10,
                padding: 12,
                borderRadius: 12,
                background: "#0d2744",
                border: "1px solid #1c4164",
              }}
            >
              <div style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 11, color: "#fff", fontWeight: 600 }}>
                <QrCode size={14} /> Customer PWA
              </div>
              <div style={{ color: "#91a6c2", fontSize: 9, margin: "7px 0" }}>
                Share your QR so customers can order, book and chat.
              </div>
              <Link
                href="/dashboard/qr"
                style={{
                  display: "inline-block",
                  border: "1px solid #2b5276",
                  background: "#153656",
                  color: "#fff",
                  borderRadius: 7,
                  padding: "6px 10px",
                  fontSize: 10,
                  textDecoration: "none",
                }}
              >
                Open QR codes
              </Link>
            </div>
          )}
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 10, color: "#7186a6", fontWeight: 800, letterSpacing: "0.12em", marginBottom: 6 }}>LANGUAGE</div>
            <select
              value={typeof window !== "undefined" ? localStorage.getItem("ago_lang") || "en" : "en"}
              onChange={(e) => setLang(e.target.value)}
              style={{
                width: "100%",
                background: "#0d2744",
                color: "#dce6f8",
                border: "1px solid #1c4164",
                borderRadius: 8,
                padding: "8px 10px",
                fontSize: 12,
              }}
            >
              {LANGUAGES.map((l: any) => (
                <option key={l.code} value={l.code}>{l.native}</option>
              ))}
            </select>
          </div>
          <button
            onClick={onLogout}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "transparent",
              color: "#aebed6",
              padding: "10px 12px",
              borderRadius: 9,
              fontSize: 12,
              textAlign: "left",
            }}
          >
            <LogOut size={16} /> Sign out
          </button>
          <div style={{ fontSize: 9, color: "#59708f", padding: "12px 4px 0" }}>v1.0.0 · Console</div>
        </div>
      </aside>
    </>
  );
}