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


## Final platform scope
The platform now includes tenant feature controls, menu/catalog management, restaurant orders and status tracking, automatic bills, customer service requests, loyalty rules, offline customer games, feedback, and Google review handoff.
