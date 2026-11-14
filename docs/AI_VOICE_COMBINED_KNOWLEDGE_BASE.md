# AI Voice — Combined Legacy + Global Knowledge Base

## Purpose

AI Voice uses both knowledge generations. The existing AI Growth OS Knowledge Library remains the source of tenant-specific approved facts and existing voice behavior. The Global Knowledge Brain adds a reusable intent taxonomy, entity/state concepts, multilingual normalization and industry packs. It is an additive layer, not a replacement or destructive migration.

## Knowledge layers and precedence

1. **Live structured tenant data** — hours, services, products, prices, staff, availability and booking records. Dynamic facts must come from live APIs/database state.
2. **Legacy tenant Knowledge Library** — approved/system `KnowledgeItem` records, tenant Business Brain instructions and approved published website content.
3. **Existing global FAQ library** — `GlobalFaq` records and `faq_seed.py` industry defaults, used only when tenant/live data has no reliable answer.
4. **Global Knowledge Brain taxonomy** — canonical intent labels and industry intent packs. This classifies the customer's goal and helps retrieval/analytics; it is not a source of tenant facts.
5. **Grounded model fallback** — only after retrieval misses; never invent prices, policies, availability, booking confirmation or payment success.
6. **Human escalation / callback** — required when confidence is low, knowledge is missing, an action fails repeatedly or the customer asks for a person.

## Existing implementation retained

- `brain.py` remains the runtime orchestrator.
- `KnowledgeItem` and `KnowledgeCandidate` remain tenant knowledge and learning records.
- `semantic_knowledge.py` remains semantic retrieval for approved tenant knowledge.
- `ai_router.py` continues lexical/structured/global FAQ matching.
- `faq_seed.py` remains the existing generic and industry FAQ seed.
- Existing booking, CRM, call and escalation handlers are not replaced.

## New Global Knowledge Brain added

- Canonical customer-intent taxonomy spanning discovery, business information, services/products, pricing, booking, confirmation/rejection, voice feedback, payment, offers, loyalty, orders, delivery, support, complaints and human handoff.
- Industry intent packs for clinics/healthcare, restaurants, salons, gyms, education, real estate, hotels and retail.
- A legacy-to-canonical crosswalk. Existing runtime intent names remain unchanged so old handlers and state transitions are not silently rerouted.
- Canonical classification is exposed as supplemental metadata for logging/analytics. It must not change booking state or action execution.

## Multilingual contract

The Global Knowledge Brain follows the research specification's language coverage: English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Urdu and Hinglish/mixed speech. Existing language detection and voice normalization remain authoritative until individually tested replacements are ready.

## Learning loop

Every turn should retain tenant, call/conversation, language, intent, knowledge source, confidence, fallback, escalation and outcome. Unanswered questions become pending `KnowledgeCandidate` records. A tenant administrator reviews and approves a candidate before it becomes reusable tenant knowledge. Do not auto-publish unverified AI answers.

## Safety and correctness invariants

- Tenant isolation is mandatory.
- Tenant-approved answers outrank global generic material.
- Dynamic data is queried live; never answer availability from static FAQs.
- Confirmation is state-dependent; “yes” alone is not a booking confirmation.
- Previous-call context must not leak into a new call.
- Voice feedback/repeat requests must not trigger business handoff.
- Sensitive/clinical queries use configured safety and escalation rules.
- No legacy knowledge is deleted or rewritten by this additive layer.
