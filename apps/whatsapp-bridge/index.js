// AI Growth OS — WhatsApp bridge (Baileys)
// Exposes a small REST API for the Super Admin WhatsApp Inbox.
// Inbound messages POST to the AI Growth OS webhook.

import express from "express";
import makeWASocket, {
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  Browsers,
} from "@whiskeysockets/baileys";
import P from "pino";
import QRCode from "qrcode-terminal";

const PORT = process.env.PORT || 8080;
const API_KEY = process.env.BRIDGE_API_KEY || "change-me-in-render";
const WEBHOOK_URL = process.env.WEBHOOK_URL || "";
const TENANT_ID = process.env.TENANT_ID || "";
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || "";

const logger = P({ level: process.env.LOG_LEVEL || "warn" });
const app = express();
app.use(express.json({ limit: "2mb" }));

// ---------------------------------------------------------------
// State (in-memory — QR rescan needed after Render restart)
// ---------------------------------------------------------------
let sock = null;
let currentQR = null;
let connectionState = "starting"; // starting | qr | connected | disconnected
let connectedPhone = null;
const authFolder = "./auth_info";

// ---------------------------------------------------------------
// Auth guard for our REST endpoints
// ---------------------------------------------------------------
function auth(req, res, next) {
  const key = req.headers["x-api-key"] || req.query.api_key;
  if (key !== API_KEY) {
    return res.status(401).json({ error: "unauthorized" });
  }
  next();
}

// ---------------------------------------------------------------
// Send inbound message to AI Growth OS webhook
// ---------------------------------------------------------------
async function forwardInbound(msg) {
  if (!WEBHOOK_URL || !TENANT_ID) {
    logger.warn("webhook not configured — dropping inbound message");
    return;
  }
    const key = msg.key || {};
  // Use remoteJidAlt if available to get the real phone number (PN), 
  // falling back to remoteJid if not present.
  const jid = key.remoteJidAlt || key.remoteJid || "";
  const from = jid.split("@")[0];
  const body =
    msg.message?.conversation ||
    msg.message?.extendedTextMessage?.text ||
    msg.message?.imageMessage?.caption ||
    msg.message?.videoMessage?.caption ||
    "";
  if (!from || !body) return;

    const payload = {
    event: "message.received",
    data: {
      id: key.id || "",
      from: from + "@c.us",
      senderPhone: from,
      chatId: (key.remoteJidAlt || key.remoteJid || ""), // Fix: prefer real phone number over LID
      body,
      isGroup: (key.remoteJid || "").endsWith("@g.us"),
      contact: { pushName: msg.pushName || "" },
    },
  };

  try {
    const r = await fetch(
      WEBHOOK_URL.replace("{tenant_id}", TENANT_ID),
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(WEBHOOK_SECRET ? { "X-OpenWA-Signature": WEBHOOK_SECRET } : {}),
        },
        body: JSON.stringify(payload),
      }
    );
    if (!r.ok) {
      logger.warn({ status: r.status }, "webhook rejected inbound");
    } else {
      logger.info({ from }, "inbound forwarded");
    }
  } catch (e) {
    logger.error({ err: e.message }, "webhook forward failed");
  }
}

// ---------------------------------------------------------------
// Baileys socket
// ---------------------------------------------------------------
async function startSocket() {
  const { state, saveCreds } = await useMultiFileAuthState(authFolder);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    logger,
    printQRInTerminal: false,
    auth: state,
    // Force a Linux browser tuple to avoid Windows-428 rejections
    browser: Browsers.ubuntu("Chrome"),
    generateHighQualityLinkPreview: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (u) => {
    const { connection, lastDisconnect, qr } = u;
    if (qr) {
      currentQR = qr;
      connectionState = "qr";
      console.log("── SCAN QR ──");
      QRCode.generate(qr, { small: true });
    }
    if (connection === "open") {
      currentQR = null;
      connectionState = "connected";
      connectedPhone = sock?.user?.id?.split(":")[0] || null;
      logger.info({ phone: connectedPhone }, "connected");
    }
    if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      logger.warn({ code }, "connection closed");
      connectionState = "disconnected";
      if (code !== DisconnectReason.loggedOut) {
        setTimeout(() => {
          startSocket().catch((e) => logger.error(e, "restart failed"));
        }, 3000);
      } else {
        logger.error("logged out — delete auth_info folder and rescan");
      }
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const m of messages) {
      if (!m.message) continue;
      if (m.key?.fromMe) continue;
      await forwardInbound(m);
    }
  });
}

// ---------------------------------------------------------------
// REST API
// ---------------------------------------------------------------

// Health + status
app.get("/", (_req, res) => {
  res.json({
    service: "ai-growth-whatsapp-bridge",
    state: connectionState,
    phone: connectedPhone,
  });
});

// QR as HTML (open in browser)
app.get("/qr", (_req, res) => {
  if (connectionState === "connected") {
    return res.send(
      `<html><body style="font-family:sans-serif;padding:40px;text-align:center">
        <h2 style="color:#1aa76c">✓ Connected</h2>
        <p>Phone: ${connectedPhone || "unknown"}</p>
      </body></html>`
    );
  }
  if (!currentQR) {
    return res.send(
      `<html><body style="font-family:sans-serif;padding:40px;text-align:center">
        <h2>Waiting for QR…</h2>
        <p>Refresh in a few seconds.</p>
        <p>State: ${connectionState}</p>
      </body></html>`
    );
  }
   const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=320x320&data=${encodeURIComponent(
    currentQR
  )}`;
  res.send(
    `<html><body style="font-family:sans-serif;padding:40px;text-align:center;background:#fafbfc">
      <h2>Scan with WhatsApp</h2>
      <p>WhatsApp → Linked devices → Link a device</p>
      <img src="${qrUrl}" alt="QR" style="border:8px solid #fff;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1)" />
      <p style="color:#75839a;font-size:12px;margin-top:20px">Refresh if this QR expires.</p>
    </body></html>`
  );
});

// Send a text message
app.post("/send", auth, async (req, res) => {
  if (connectionState !== "connected" || !sock) {
    return res.status(503).json({ error: "not connected" });
  }
  const { to, text } = req.body || {};
  if (!to || !text) return res.status(400).json({ error: "to and text required" });
  const jid = to.includes("@") ? to : `${to.replace(/\D/g, "")}@s.whatsapp.net`;
  try {
    const result = await sock.sendMessage(jid, { text });
    res.json({ ok: true, id: result?.key?.id });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// OpenWA-compatible session status endpoint
app.get("/api/sessions/:session_id", auth, (req, res) => {
  if (connectionState === "connected") {
    return res.json({
      status: "connected",
      session_id: req.params.session_id,
      phoneNumber: connectedPhone,
    });
  }
  res.json({
    status: connectionState === "qr" ? "qr_pending" : connectionState,
    session_id: req.params.session_id,
    phoneNumber: null,
  });
});

// OpenWA-compatible send-text endpoint (so existing backend keeps working)
app.post("/api/sessions/:session_id/messages/send-text", auth, async (req, res) => {
  if (connectionState !== "connected" || !sock) {
    return res.status(503).json({ error: "not connected" });
  }
  const { chatId, text } = req.body || {};
  if (!chatId || !text) {
    return res.status(400).json({ error: "chatId and text required" });
  }
  const jid = chatId.includes("@") ? chatId : `${chatId.replace(/\D/g, "")}@s.whatsapp.net`;
  try {
    const result = await sock.sendMessage(jid, { text });
    res.json({ ok: true, id: result?.key?.id, chatId });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// Manual QR reset (delete session + restart)
app.post("/reset", auth, async (req, res) => {
  try {
    if (sock) {
      try { await sock.logout(); } catch {}
      try { sock.end?.(); } catch {}
    }
    const fs = await import("fs");
    fs.rmSync(authFolder, { recursive: true, force: true });
    connectionState = "starting";
    currentQR = null;
    connectedPhone = null;
    setTimeout(() => startSocket().catch((e) => logger.error(e, "restart failed")), 500);
    res.json({ ok: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

// ---------------------------------------------------------------
// Boot
// ---------------------------------------------------------------
app.listen(PORT, () => {
  logger.info({ port: PORT }, "bridge listening");
  startSocket().catch((e) => logger.error(e, "socket start failed"));
});