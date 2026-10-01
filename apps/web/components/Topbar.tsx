"use client";
import { useState } from "react";
import { Menu, Search, Bell, CircleHelp, ChevronDown, LogOut } from "lucide-react";

export default function Topbar({
  userName,
  role,
  onOpenSidebar,
  onLogout,
}: {
  userName: string;
  role: string;
  onOpenSidebar: () => void;
  onLogout: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const isAdmin = role === "platform_admin" || role === "super_admin";

  return (
    <header
      style={{
        height: 70,
        background: "#fff",
        borderBottom: "1px solid #e7ebf2",
        display: "flex",
        alignItems: "center",
        gap: 18,
        padding: "0 28px",
        position: "sticky",
        top: 0,
        zIndex: 20,
      }}
    >
      <button
        onClick={onOpenSidebar}
        className="ago-hamburger"
        style={{
          background: "transparent",
          color: "#62718a",
          padding: 8,
          display: "none",
          borderRadius: 8,
        }}
      >
        <Menu size={20} />
      </button>

      <div
        style={{
          height: 38,
          maxWidth: 420,
          flex: 1,
          display: "flex",
          alignItems: "center",
          gap: 8,
          border: "1px solid #e2e7ef",
          background: "#fafbfd",
          borderRadius: 8,
          padding: "0 12px",
          color: "#8290a7",
        }}
      >
        <Search size={17} />
        <input
          placeholder="Search…"
          style={{
            border: 0,
            outline: 0,
            background: "transparent",
            width: "100%",
            fontSize: 12,
            color: "#26324b",
            padding: 0,
            margin: 0,
          }}
        />
      </div>

      <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, position: "relative" }}>
        <button
          style={{
            background: "transparent",
            color: "#62718a",
            padding: 8,
            borderRadius: 8,
            position: "relative",
          }}
        >
          <Bell size={18} />
          <span
            style={{
              position: "absolute",
              width: 6,
              height: 6,
              background: "#5b5cf0",
              borderRadius: "50%",
              right: 8,
              top: 8,
            }}
          />
        </button>
        <button
          style={{ background: "transparent", color: "#62718a", padding: 8, borderRadius: 8 }}
        >
          <CircleHelp size={18} />
        </button>

        <button
          onClick={() => setMenuOpen(!menuOpen)}
          style={{
            background: "transparent",
            color: "#17213a",
            padding: "4px 8px",
            display: "flex",
            alignItems: "center",
            gap: 8,
            borderRadius: 8,
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: "50%",
              display: "grid",
              placeItems: "center",
              background: "#e8edf8",
              color: "#21355d",
              fontWeight: 800,
              fontSize: 11,
            }}
          >
            {isAdmin ? "SS" : "SN"}
          </div>
          <div style={{ textAlign: "left", minWidth: 95 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#17213a", lineHeight: 1.1 }}>{userName}</div>
            <div style={{ fontSize: 9, color: "#8190a8", marginTop: 2 }}>
              {isAdmin ? "Super Admin" : "Business admin"}
            </div>
          </div>
          <ChevronDown size={14} color="#8190a8" />
        </button>

        {menuOpen && (
          <div
            onMouseLeave={() => setMenuOpen(false)}
            style={{
              position: "absolute",
              top: 50,
              right: 0,
              background: "#fff",
              border: "1px solid #e8ecf3",
              borderRadius: 10,
              boxShadow: "0 12px 30px rgba(17,24,39,0.08)",
              minWidth: 180,
              padding: 6,
              zIndex: 100,
            }}
          >
            <button
              onClick={() => {
                setMenuOpen(false);
                onLogout();
              }}
              style={{
                width: "100%",
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: "transparent",
                color: "#c74646",
                padding: "10px 12px",
                borderRadius: 8,
                fontSize: 12,
                textAlign: "left",
              }}
            >
              <LogOut size={15} /> Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}