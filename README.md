# AI Growth OS

Multi-tenant AI customer engagement platform for local businesses.

## Phase 1

Phase 1 establishes the production foundation:

- Next.js customer PWA and business dashboard shell
- FastAPI backend
- PostgreSQL-ready multi-tenant data model
- Tenant/business onboarding
- Industry templates
- Customer identity and CRM foundations
- AI chat interface with safe provider abstraction
- Lead detection and dashboard
- QR entry points
- Docker development environment

## Architecture

```
Customer PWA / Dashboard
        |
     Next.js
        |
      FastAPI
        |
 PostgreSQL + Redis
        |
 AI / WhatsApp / Payments / Voice adapters
```

## Local development

### Backend

```bash
cd apps/api
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
```

### Database

```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d
```

See `docs/PHASE_1.md` for the implementation contract.


## Tenant integrations

The Business Admin dashboard now exposes a simple **Settings → Integrations** experience.

Platform defaults can be used without tenant credentials. A tenant can optionally connect its own account/provider. Tenant configuration takes precedence over the platform default.

Supported integration choices include:
- Built-in WhatsApp (OpenWA) and Meta WhatsApp Cloud API
- Razorpay
- Gemini
- OpenAI / ChatGPT API
- OpenRouter
- Claude / Anthropic
- Meta Business / Facebook / Instagram / Meta Ads
- YouTube
- Google Business Profile
- Email / SMTP
- Voice & Calling

Secrets are encrypted at rest and status responses never return raw secret values.

### AI routing policy

The AI Router itself is **tokenless**. It performs language/intent detection and deterministic matching only.

The response order is:

1. Structured tenant data
2. Tenant Business Knowledge Library
3. Global approved FAQ library
4. Last-resort AI provider pool

Model tokens are therefore reserved for cases where the verified library cannot answer the customer. A tenant-owned AI provider is used before the platform fallback pool. Platform AI providers can be prioritized by Super Admin and failed/rate-limited providers are skipped.

### Platform environment variables

Use a Fernet key for encrypted integration credentials:

```bash
INTEGRATION_CREDENTIAL_ENCRYPTION_KEY=<fernet-key>
WHATSAPP_CREDENTIAL_ENCRYPTION_KEY=<existing-fernet-key>
```

Optional platform AI fallbacks:

```bash
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.6-luna
OPENROUTER_API_KEY=
OPENROUTER_MODEL=qwen/qwen3-coder
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-3-5-haiku-latest
```

Built-in WhatsApp uses the platform OpenWA service:

```bash
OPENWA_BASE_URL=http://localhost:2785
OPENWA_API_KEY=
```

The tenant never sees the platform OpenWA URL/API key/session credentials. The Business Admin only enters its WhatsApp number and connects by pairing code or QR.


## Social Studio

The tenant dashboard links to **Social Studio** for connected-account publishing and analytics:

- Facebook Page publishing
- Instagram image publishing
- Meta Ads campaign insights
- YouTube video upload through resumable OAuth upload
- Google Business Profile local posts and location discovery
- Provider health checks
- Provider-side OAuth revocation plus local secret removal

API routes are tenant-scoped under `/api/v1/tenants/{tenant_id}/social/*`.

Google OAuth uses offline access so the service can refresh access tokens without requiring the tenant to reconnect each time. YouTube's upload API requires OAuth authorization and unverified API projects may be restricted to private uploads until Google's audit requirements are satisfied.

Google Business Profile API access is subject to Google's eligibility and API access requirements; the implementation does not bypass those requirements.
