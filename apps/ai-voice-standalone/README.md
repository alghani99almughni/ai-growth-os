# AI Voice — standalone application

AI Voice is packaged as **one Render web service**. The Next.js frontend and FastAPI backend run in the same container behind Nginx; browser API requests and WebSocket calls are routed internally to FastAPI.

## Render architecture

- **One application web service:** `ai-voice` (Next.js + FastAPI in one Docker container).
- **One dedicated PostgreSQL database:** `ai-voice-db` (managed data resource, not an application server).
- **One managed Redis resource:** `ai-voice-redis` (managed data resource, not an application server).
- **Local inference:** the existing Ollama + local-voice engine is not bundled into this web container. It needs model storage and sufficient CPU/RAM/GPU. It can initially run on a separately provisioned inference machine/service and connect privately to the API. Do not assume the Free zero-paid-token call path is production-ready until this connection is configured and tested.

## Application workspaces

- `/` — public product landing page.
- `/login` — shared sign-in; platform administrators are routed to the Super Admin console and tenant users to the client workspace.
- `/dashboard/ai-voice` — client Free / Paid voice-agent workspace.
- `/platform/ai-voice` — Super Admin Free / Paid / DID-SIP control console.

New tenant accounts are provisioned by the platform administrator; public self-service registration is not enabled.

## Current production gates

The UI and control-plane configuration are not the same as a live voice service. Do not mark the product production-ready until all of the following are verified:

- The local inference sidecar is privately provisioned and connected to the browser voice runtime. The current sidecar is a prototype and its README explicitly records that live WebRTC/PSTN routing is not yet wired.
- A complete call uses local STT, local LLM and local TTS without invoking a paid AI inference provider on the Free plan.
- Paid provider selection is connected to platform-controlled provider activation, credentials, limits and billing enforcement.
- DID/SIP provider registration, inbound/outbound call routing and health checks are implemented and tested. Current DID/SIP APIs store inventory and assignments only.
- Whole-call recording, transcript persistence, CRM linkage, callback/handoff and tenant isolation pass end-to-end tests.
- `/health` and `/ready` both pass against the dedicated Render database and Redis.

The Docker image build now includes an API import and route-registration smoke test. CI must pass after the latest branch changes before deployment.
## Deploy

1. Select the `ai-voice` branch in Render.
2. Create a Blueprint using `render.ai-voice.yaml`.
3. Confirm it creates only one `ai-voice` web service, one PostgreSQL database and one Redis resource.
4. Configure the required secret environment variables in Render.
5. Verify `/health` and `/ready`, then run authentication, tenant-isolation, browser-call and WebSocket tests before onboarding clients.

The Dockerfile is `deploy/ai-voice/Dockerfile`. Nginx routes `/api/*`, `/ws/*`, health and documentation endpoints to FastAPI, and all other paths to Next.js.

## Vercel alternative

Vercel can host the Next.js frontend, but then the FastAPI API must be hosted separately. That is not the one-application-server option. For a single web service, use the Render Docker blueprint.

## Local frontend development

```bash
cd apps/ai-voice-standalone/web
npm install
npm run dev
```

## Separation and safety

- Deploy only from `ai-voice`.
- Do not connect to AI Growth OS production database, Redis, API or frontend.
- No changes to `main` and no deployment has been performed by this work.
- Set unique secrets and a dedicated database for AI Voice.
- Carrier, DID/SIP, hosting, hardware and network costs are separate from AI inference-token costs.
