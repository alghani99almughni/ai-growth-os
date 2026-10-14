"use client";

export default function PlatformWhatsAppInboxPage() {
  return (
    <div style={{ maxWidth: 1000 }}>
      <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
        WhatsApp Inbox
      </h1>
      <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
        Your WhatsApp chats — 1:1 and group conversations with reply.
      </p>
      <div style={{ marginTop: 24, padding: 40, textAlign: "center", background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, color: "#98a2b4", fontSize: 13 }}>
        Coming in the next PR — WhatsApp Web-style chats.
      </div>
    </div>
  );
}