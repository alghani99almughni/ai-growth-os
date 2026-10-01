# Three-channel customer identity and WhatsApp configuration

## Locked customer entry model

AI Growth OS accepts customers through exactly three primary channels:

1. PWA
2. WhatsApp
3. Phone / landline

All three converge on the same Tenant-scoped Customer 360. The CRM/database is the source of truth; channels are only entry/communication surfaces.

## Identity gate

The platform-wide identity invariant is:

- Mobile number: REQUIRED
- Customer name: REQUIRED

No customer-specific CRM/business action may proceed until both are captured. The backend must enforce this independently of UI behavior.

Verification is separate from capture. OTP or stronger verification can be required for sensitive actions.

## Channel behavior

### PWA
Capture mobile number and name before customer-specific chat, booking, ordering, loyalty, payment or service actions.

### WhatsApp
The incoming WhatsApp sender supplies the channel number. The system resolves the Customer 360 record. If the customer is new and no usable name is available, ask for the name before creating the customer record or performing business actions.

### Phone / landline
The voice flow must capture a usable mobile number and name. Caller ID may be retained as a call-source identifier, but it is not a substitute for the required mobile number.

## WhatsApp is a channel, not the source of truth

WhatsApp is optional/secondary. Customers can start with WhatsApp or choose to continue from PWA to WhatsApp. Business data, CRM, bookings, orders, payments and loyalty remain in AI Growth OS.

## OpenWA provider

OpenWA is the default self-hosted WhatsApp provider.

Provider abstraction:

- OpenWAProvider: self-hosted/unofficial WhatsApp Web gateway
- MetaProvider: official WhatsApp Business Platform fallback

AI tools must call the AI Growth OS WhatsApp adapter, never OpenWA directly.

## CRM welcome message

When a new customer is created in the Business Admin customer-creation flow:

1. Store mobile + name.
2. Attempt the configured WhatsApp welcome message.
3. The response reports whether the welcome send succeeded.
4. The welcome message points the customer to both WhatsApp continuation and the PWA.

The welcome automation is configurable with WHATSAPP_WELCOME_ENABLED.

## Inbound WhatsApp

OpenWA sends message.received webhooks to:

POST /api/v1/webhooks/openwa/{tenant_id}

The webhook is HMAC verified against the raw body and should be configured with OpenWA's X-OpenWA-Signature: sha256=<hex> header.

The inbound flow is:

WhatsApp -> OpenWA -> signed webhook -> Customer identity -> AI Growth OS -> CRM/business tools -> OpenWA reply

OpenWA webhook idempotency keys should be deduplicated before production scale-out.

## OpenWA deployment note

OpenWA is self-hosted and free/open-source, but it uses unofficial WhatsApp clients and therefore carries account restriction/ban risk. Use dedicated business numbers, customer-initiated/opt-in conversations where applicable, conservative rate limits, and retain Meta Cloud API as the production fallback for critical use cases.
