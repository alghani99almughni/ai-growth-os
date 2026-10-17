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
const PAIRING_PHONE = process.env.PAIRING_PHONE || "";
const TENANT_ID = process.env.TENANT_ID || "tenant_1";

const logger = P({ level: process.env.LOG_LEVEL || "warn" });
const app = express();
app.use(express.json({ limit: "2mb" }));

let sock = null;
let currentQR = null;
let pairingCode = null;
let pairingRequested = false;
let connectionState = "starting"; 
let connectedPhone = null;
const authFolder = "./auth_info";

function auth(req, res, next) {
  const key = req.headers["x-api-key"] || req.query.api_key;
  if (key !== API_KEY) return res.status(401).json({ error: "unauthorized" });
  next();
}

async function forwardInbound(msg) {
  if (!WEBHOOK_BASE_URL) return;
  const key = msg.key || {};
  const jid = key.remoteJidAlt || key.remoteJid || "";
  const from = jid.split("@")[0];
  const body = msg.message?.conversation || msg.message?.extendedTextMessage?.text || "";
  if (!from || !body) return;

  const payload = {
    event: "message.received",
    data: { id: key.id, senderPhone: from, body: body, contact: { pushName: msg.pushName || "" } },
  };

  try {
    const url = WEBHOOK_BASE_URL.replace("{tenant_id}", TENANT_ID);
    await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    logger.info({ from }, "inbound forwarded");
  } catch (e) {
    logger.error({ err: e.message }, "webhook forward failed");
  }
}

async function startSocket() {
  const { useMultiFileAuthState } = await import("@whiskeysockets/baileys");
  const { state, saveCreds } = await useMultiFileAuthState(authFolder);

  // FORCING the version that worked successfully on 8790153319
  const version = [2, 3000, 1043857760]; 

  sock = makeWASocket({
    version,
    logger,
    printQRInTerminal: false,
    auth: state,
    browser: Browsers.ubuntu("Chrome"),
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (u) => {
    const { connection, lastDisconnect, qr } = u;

    if (connection === "connecting") connectionState = "connecting";

    if ((qr || connection === "connecting") && PAIRING_PHONE && !state.creds.registered && !pairingRequested) {
      pairingRequested = true;
      try {
        pairingCode = await sock.requestPairingCode(PAIRING_PHONE.replace(/\D/g, ""));
        connectionState = "pairing_code";
        console.log(`\n=== WHATSAPP PAIRING CODE: ${pairingCode} ===\n`);
      } catch (err) {
        pairingRequested = false;
      }
    }

    if (qr && !PAIRING_PHONE) {
      currentQR = qr;
      connectionState = "qr";
      QRCode.generate(qr, { small: true });
    }

    if (connection === "open") {
      currentQR = null; pairingCode = null; pairingRequested = false;
      connectionState = "connected";
      connectedPhone = sock?.user?.id?.split(":")[0] || null;
    }

    if (connection === "close") {
      const code = lastDisconnect?.error?.output?.statusCode;
      connectionState = "disconnected";
      pairingRequested = false;
      if (code !== DisconnectReason.loggedOut) {
        setTimeout(startSocket, 3000);
      }
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const m of messages) {
      if (m.message && !m.key?.fromMe) await forwardInbound(m);
    }
  });
}

app.get("/", (_req, res) => res.json({ state: connectionState, phone: connectedPhone, code: pairingCode }));

app.get("/reset", auth, async (req, res) => {
  if (sock) {
    try { await sock.logout(); } catch {}
    try { sock.end?.(); } catch {}
  }
  fs.rmSync(authFolder, { recursive: true, force: true });
  connectionState = "starting"; currentQR = null; pairingCode = null; pairingRequested = false; connectedPhone = null;
  setTimeout(startSocket, 500);
  res.json({ ok: true });
});

app.listen(PORT, () => {
  logger.info({ port: PORT }, "bridge listening");
  startSocket().catch((e) => logger.error(e, "socket start failed"));
});