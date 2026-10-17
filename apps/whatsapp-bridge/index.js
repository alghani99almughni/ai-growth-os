// AI Growth OS — Multi-Tenant WhatsApp bridge (Baileys)
import express from "express";
import makeWASocket, {
  DisconnectReason,
  fetchLatestWaWebVersion,
  Browsers,
} from "@whiskeysockets/baileys";
import P from "pino";
import QRCode from "qrcode-terminal";
import fs from "fs";

const PORT = process.env.PORT || 8080;
const API_KEY = process.env.BRIDGE_API_KEY || "change-me-in-render";
const WEBHOOK_BASE_URL = process.env.WEBHOOK_BASE_URL || "";
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || "";

const logger = P({ level: process.env.LOG_LEVEL || "warn" });
const app = express();
app.use(express.json({ limit: "2mb" }));

const sessions = new Map(); 

function auth(req, res, next) {
  const key = req.headers["x-api-key"] || req.query.api_key;
  if (key !== API_KEY) return res.status(401).json({ error: "unauthorized" });
  next();
}

async function forwardInbound(msg, tenantId) {
  if (!WEBHOOK_BASE_URL || !tenantId) return;
  
  const key = msg.key || {};
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
      chatId: jid,
      body,
      isGroup: (key.remoteJid || "").endsWith("@g.us"),
      contact: { pushName: msg.pushName || "" },
    },
  };

  try {
    const url = WEBHOOK_BASE_URL.replace("{tenant_id}", tenantId);
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(WEBHOOK_SECRET ? { "X-OpenWA-Signature": WEBHOOK_SECRET } : {}),
      },
      body: JSON.stringify(payload),
    });
    if (!r.ok) logger.warn({ status: r.status, tenantId }, "webhook rejected inbound");
  } catch (e) {
    logger.error({ err: e.message }, "webhook forward failed");
  }
}

async function startSession(tenantId, phoneNumber) {
  const authFolder = `./auth_info/${tenantId}`;
  
  const { useMultiFileAuthState } = await import("@whiskeysockets/baileys");
  const { state, saveCreds } = await useMultiFileAuthState(authFolder);
  
  // FIX 1: Use fetchLatestWaWebVersion instead of fetchLatestBaileysVersion
  const version = [2, 3000, 1042466098]; // Known working version (as of 2026-07)

  const sock = makeWASocket({
    version,
    logger,
    printQRInTerminal: false,
    auth: state,
    browser: Browsers.ubuntu("Chrome"),
    generateHighQualityLinkPreview: false,
  });

  const sessionData = {
    sock,
    state,
    phoneNumber,
    pairingCode: null,
    connectionState: "starting",
    connectedPhone: null,
    pairingRequested: false
  };
  
  sessions.set(tenantId, sessionData);

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (u) => {
    const { connection, lastDisconnect, qr } = u;

    if (connection === "connecting") {
        sessionData.connectionState = "connecting";
    }

    // FIX 2: Trigger pairing code on QR event AND connection state
    if ((qr || connection === "connecting") && phoneNumber && !state.creds.registered && !sessionData.pairingRequested) {
      sessionData.pairingRequested = true;
      try {
        const digits = phoneNumber.replace(/\D/g, "");
        sessionData.pairingCode = await sock.requestPairingCode(digits);
        sessionData.connectionState = "pairing_code";
        console.log(`\n[${tenantId}] WHATSAPP PAIRING CODE: ${sessionData.pairingCode}\n`);
      } catch (err) {
        console.error(`[${tenantId}] pairing code failed:`, err.message);
        sessionData.pairingRequested = false;
      }
    }

    if (qr && !phoneNumber) {
      sessionData.pairingCode = null;
      sessionData.connectionState = "qr";
      console.log(`\n[${tenantId}] SCAN QR`);
      QRCode.generate(qr, { small: true });
    }

    if (connection === "open") {
      sessionData.pairingCode = null;
      sessionData.pairingRequested = false;
      sessionData.connectionState = "connected";
      sessionData.connectedPhone = sock?.user?.id?.split(":")[0] || null;
      logger.info({ tenantId, phone: sessionData.connectedPhone }, "connected");
    }

    if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      sessionData.connectionState = "disconnected";
      sessionData.pairingRequested = false;
      
      if (code !== DisconnectReason.loggedOut) {
        setTimeout(() => startSession(tenantId, phoneNumber), 3000);
      } else {
        logger.error(`[${tenantId}] logged out — delete auth_info folder`);
      }
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const m of messages) {
      if (!m.message || m.key?.fromMe) continue;
      await forwardInbound(m, tenantId);
    }
  });
}

app.post("/api/connect", auth, async (req, res) => {
  const { tenantId, phone } = req.body || {};
  if (!tenantId || !phone) return res.status(400).json({ error: "tenantId and phone required" });
  
  if (sessions.has(tenantId)) {
    return res.status(400).json({ error: "Session already exists" });
  }

  startSession(tenantId, phone);
  res.json({ ok: true, message: "Session starting" });
});

app.get("/api/sessions/:tenantId/status", auth, (req, res) => {
  const session = sessions.get(req.params.tenantId);
  if (!session) return res.status(404).json({ error: "Session not found" });
  
  res.json({
    state: session.connectionState,
    code: session.pairingCode,
    phone: session.connectedPhone
  });
});

app.post("/api/sessions/:tenantId/messages/send-text", auth, async (req, res) => {
  const session = sessions.get(req.params.tenantId);
  if (!session || session.connectionState !== "connected") {
    return res.status(503).json({ error: "not connected" });
  }
  
  const { chatId, text } = req.body || {};
  if (!chatId || !text) return res.status(400).json({ error: "chatId and text required" });
  
  const jid = chatId.includes("@") ? chatId : `${chatId.replace(/\D/g, "")}@s.whatsapp.net`;
  try {
    const result = await session.sock.sendMessage(jid, { text });
    res.json({ ok: true, id: result?.key?.id, chatId });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post("/api/sessions/:tenantId/reset", auth, async (req, res) => {
  const session = sessions.get(req.params.tenantId);
  if (session) {
    try { await session.sock.logout(); } catch {}
    try { session.sock.end?.(); } catch {}
    
    fs.rmSync(`./auth_info/${req.params.tenantId}`, { recursive: true, force: true });
    sessions.delete(req.params.tenantId);
  }
  res.json({ ok: true });
});

app.listen(PORT, () => {
  logger.info({ port: PORT }, "bridge listening");
});