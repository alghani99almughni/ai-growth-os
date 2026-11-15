# AI Voice — Standalone deployment

This application is an independent marketing and onboarding entry point in the monorepo. It does not replace the existing AI Growth OS web app or its routes.

## Frontend

- Vercel project root: `apps/ai-voice-standalone/web`
- Framework: Next.js 15
- Build: `npm run build`
- Start: `npm start`
- No paid AI provider key is required to render the landing page.
- Contact actions currently use `contact@aigrowthos.com`.

## Render

A separate blueprint is provided at `render.ai-voice.yaml`. It defines separately named AI Voice API and web services and a dedicated Postgres database. Review the environment variables and set secrets in Render before deploying. The API service reuses the existing FastAPI application code, so its full environment requirements and migrations must be checked against the target database before production traffic is enabled.

## Important separation

- Deploy only from the `ai-voice` branch.
- Do not connect this blueprint to the existing AI Growth OS production database, Redis, API or frontend services.
- Set a unique `DATABASE_URL`, `JWT_SECRET`, `ALLOWED_ORIGINS`, `PUBLIC_APP_URL` and any required encryption/provider secrets.
- Set the standalone frontend `NEXT_PUBLIC_API_URL` to the new AI Voice API URL.
- The current landing page is a product website, not yet a verified tenant sign-up/login flow. Authentication, tenant provisioning and complete call runtime must be validated separately before accepting customers.
- Zero-paid-AI-token Free inference is only achieved when the local STT/LLM/TTS runtime is provisioned and selected. Carrier, DID/SIP, hosting, hardware and network costs are separate.

## Local frontend check

```bash
cd apps/ai-voice-standalone/web
npm install
npm run build
npm run dev
```
