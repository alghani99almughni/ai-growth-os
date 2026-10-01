# AI Customer Engagement Engine

## Runtime decision flow

Customer message/voice transcript -> language detection -> tenant context -> deterministic business data -> global FAQ retrieval -> tenant FAQ/knowledge -> LLM reasoning -> controlled business action -> CRM -> response.

The cost router intentionally checks deterministic and FAQ paths before Gemini. This keeps repetitive questions away from the LLM and preserves tokens.

## Knowledge hierarchy

1. Structured tenant data: profile, services, products, hours, policies and booking rules.
2. Global FAQ library: reusable industry questions and intents.
3. Tenant knowledge: business-specific FAQs and documents.
4. Conversation memory: current language, intent, state and message history.

Tenant data wins over generic global content when the two conflict.

## Multilingual voice

The API detects the customer's language and stores it on the conversation. The initial supported language catalog includes English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Urdu, Odia and Assamese.

Voice transport is WebRTC with STUN/TURN support. Speech-to-text and text-to-speech are provider adapters so providers can change without changing the customer workflow.

For PSTN/mobile phone answering, a telephony/SIP provider must connect the phone number to the same conversation engine. Browser WebRTC alone does not receive ordinary cellular calls.

## AI correctness

The model must not invent prices, availability, booking success, payment success, discounts, policies, or professional advice outside approved business knowledge. Actions are performed by backend tools and confirmed before the assistant says they succeeded.

## Human handoff

AI is the first answering layer. Handoff is triggered by intent, explicit human request, configured escalation rules, or an action requiring staff. The conversation ID lets staff retrieve the transcript and context.

## FAQ library

faq_seed.py is the starter corpus. It is original structured data rather than copied website content. The global_faqs table is designed to grow by industry, language and intent.

For a large global corpus, ingest curated/original FAQ records in batches and index them by language, industry, intent and keywords. A future embedding index can be added behind faq_match without changing the customer API.
