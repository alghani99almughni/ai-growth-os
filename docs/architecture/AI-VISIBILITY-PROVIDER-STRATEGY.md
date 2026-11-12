# AI Visibility Provider Strategy

## Status
Decision and implementation plan only. This document does not mean provider integrations are implemented or production-ready.

## Guardrails
- Keep the AEO/GEO feature inside the existing AI Growth OS.
- Continue on `feature/aeo-geo-visibility-platform`; do not modify `main` or deploy production.
- Reuse the application's existing authentication, tenant boundaries, provider/configuration patterns, database and job conventions.
- Do not add a second orchestration system unless a tested need is demonstrated.
- Keep provider API keys server-side and never expose secrets to the browser.
- Store method, provider/model, query, locale, timestamp, status, response evidence, citations, and errors for each observation.
- Separate model-only samples, search-grounded observations, official Search Console metrics, and deterministic website audits. Do not represent them as equivalent signals.
- A missing mention in a sample is not proof of universal invisibility and no provider score guarantees rankings.

## Provider roles and evaluation order

| Priority | Platform / channel | Initial role | Evidence to retain | Key limitation |
|---|---|---|---|---|
| 1 | Google Search Console and official Google reporting | Search performance and eligible AI-feature reporting where the account/API exposes it | Official metrics, property, date range, dimensions and source | Access depends on property verification, API/report availability and Google's reporting definitions. Do not infer AI-feature data from ordinary web clicks. |
| 2 | Gemini API with Google Search grounding | Search-grounded, repeatable test prompts | Exact prompt, model, answer, source citations/URLs, grounded search metadata and usage | Grounded API answers are not guaranteed to match the Gemini consumer app or Google Search AI Overviews/AI Mode. Follow Google grounding attribution and display requirements. |
| 3 | Perplexity API / supported search interface | Search-grounded test prompts and citations | Exact prompt, endpoint/mode, answer, citations, timestamps and errors | API results may differ from consumer UI; validate current API capabilities, terms and pricing before implementation. |
| 4 | xAI Grok API | Additional provider-specific answer samples | Exact model/mode, prompt, answer, any returned citations and errors | Do not claim to measure X/Grok consumer rankings unless an official supported endpoint exposes that data. |
| 5 | Anthropic Claude API | Optional answer sample and evidence-based analysis of collected results | Model, prompt, answer, source evidence supplied/returned and analysis provenance | A model-only answer is not a live-search visibility measurement unless an explicitly supported search tool is used and its evidence is captured. |
| 6 | Hermes Agent | Optional orchestration candidate after provider adapters exist | Workflow run ID, tools invoked, per-step status, audit trail | Agent framework is not itself an AI search visibility data source. Adopt only if it fits existing application patterns and reduces operational complexity. |

Provider priority is an evaluation order, not a promise of integration availability or a permanent product ranking.

## Measurement design

Each visibility observation should be attributable to:
- tenant and brand;
- query text, locale/region, intent/topic and test-set version;
- provider, API endpoint/mode and model where available;
- observation type: `website_audit`, `official_search_console`, `search_grounded`, or `model_sampled`;
- run time, status, latency and provider usage/cost metadata where available;
- answer text or a retention-safe excerpt, observed brand/competitor mentions, citation URLs and titles where provided;
- errors, partial-result state, and the evidence used to produce any score.

Keep raw response retention limited to what is needed and allowed by each provider's terms. Respect provider attribution, display and retention requirements. Avoid storing secrets or unnecessary personal data.

## Initial delivery sequence

1. Verify existing provider abstraction/configuration, auth, tenant guards, migrations, job conventions, and current billing/usage controls.
2. Keep the current deterministic website audit separate; address its outstanding SSRF/DNS-rebinding risk before enabling untrusted URL fetching in production.
3. Define a provider-neutral observation contract and unit tests without requiring live API keys.
4. Add a Gemini grounded proof-of-capability behind server-side configuration, preserving citations and required Google Search attribution/suggestions.
5. Add official Search Console reporting only where the supported API/report and user's verified property permit it. Keep this separate from Gemini API tests.
6. Evaluate Perplexity and Grok API access, citation behavior, regional controls, terms, limits and cost; add adapters only after passing the same contract tests.
7. Use Claude for analysis only with explicit provenance. Evaluate Hermes after the adapters work; do not introduce it as a mandatory dependency.
8. Add tenant-isolation, retry/idempotency, provider timeout, rate-limit, usage-cost, citation parsing, failure/partial-result and regression tests.
9. Run frontend/backend CI, migration and rollback tests, security review, and measured load/performance tests. Record evidence before requesting release approval.

## Acceptance criteria before production
- No cross-tenant access to brands, queries, runs, answers or citations.
- No provider secrets in frontend bundles, logs or persisted response payloads.
- Every observation labels its provider, method, timestamp and evidence.
- Provider failure, unsupported access, empty citations and partial responses are represented honestly.
- Google Search grounding requirements are followed when applicable, including required Search suggestions/attribution display.
- Rate limits, budget controls and tenant usage accounting are tested.
- SSRF/DNS-rebinding protections for website audits are proven with tests and a connection strategy that prevents a second, unvalidated DNS resolution.
- CI passes on the feature branch; preview verification, migration/rollback tests and explicit go-live approval are complete.

## Official references
- Gemini grounding with Google Search: https://ai.google.dev/gemini-api/docs/google-search
- Gemini tools overview: https://ai.google.dev/gemini-api/docs/tools
- Google Search Console help: https://support.google.com/webmasters/
- Perplexity API documentation: https://docs.perplexity.ai/
- xAI API documentation: https://docs.x.ai/
- Anthropic API documentation: https://docs.anthropic.com/
- Hermes Agent project documentation: https://github.com/hermes-agent-org/hermes
