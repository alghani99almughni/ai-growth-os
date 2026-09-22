# Architecture Independence
AI Growth OS owns tenant, knowledge, CRM, orchestration, learning, analytics, authentication and business workflows. External AI, voice, messaging, payment and transport providers are replaceable adapters, never the business core.
## Non-negotiable rule
No critical workflow may depend on a provider's free tier. If pricing, limits, API behavior or availability changes, replace the adapter without changing the customer workflow or tenant data model.
## Voice
The existing voice workflow remains intact. Realtime transport such as LiveKit is optional behind an AI Growth OS voice gateway, not a core product dependency.
## AI
Structured tenant data -> approved knowledge -> global FAQ -> provider adapter -> human callback. AI is the exception path; knowledge is the default path.
## Ownership
Customers, transcripts, calls, knowledge candidates, approved knowledge, tenant settings and analytics remain in our database.
