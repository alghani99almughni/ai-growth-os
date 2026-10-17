# AI Growth OS — WhatsApp Bridge

Baileys-based WhatsApp gateway. Runs as a separate Render service.

## Endpoints

- `GET /` — service + connection status
- `GET /qr` — scan QR from browser
- `POST /send` — `{ to, text }` → send message
- `GET /api/sessions/:id` — OpenWA-compatible status
- `POST /api/sessions/:id/messages/send-text` — OpenWA-compatible send
- `POST /reset` — wipe session, regenerate QR

All endpoints require `X-API-Key` header (except `/`, `/qr`).

## Environment

- `BRIDGE_API_KEY` — required for auth
- `WEBHOOK_URL` — AI Growth OS webhook (uses `{tenant_id}` placeholder)
- `TENANT_ID` — which tenant to forward inbound messages to
- `WEBHOOK_SECRET` — optional, sent as X-OpenWA-Signature

## Render Free caveats

- Spins down after 15 min idle → session files lost → **rescan QR**
- WebSocket to WhatsApp may keep service awake
- For production, upgrade to Starter or move to Railway/VPS