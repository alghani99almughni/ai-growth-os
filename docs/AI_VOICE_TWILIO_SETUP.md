# Twilio phone voice adapter — setup and current scope

The Twilio adapter is an additive PSTN entry point into AI Growth OS. It does not replace the existing PWA/WebRTC voice runtime.

## Required environment

Configure these values in the API service before enabling the endpoint:

- `AI_VOICE_ENABLED=true`
- `TELEPHONY_API_KEY=<Twilio Auth Token>` — used to validate Twilio's signed incoming-call webhook
- `STT_API_KEY=<Deepgram API key>`
- `TTS_API_KEY=<Deepgram API key>` (may use the same Deepgram key as STT)
- `OPENAI_API_KEY=<OpenAI API key>`
- `API_PUBLIC_URL=https://<public-api-host>` — must be HTTPS so the generated media URL is WSS

Do not commit provider secrets to Git.

## Configure a tenant DID

1. Create a platform-owned trunk record with provider `twilio` (the existing control-plane form also asks for a registrar host; for this Media Streams adapter it is metadata only and is not used to register a SIP endpoint).
2. Add the Twilio number to platform DID inventory in E.164 format, for example `+919876543210`.
3. Assign the DID to the target tenant and a published AI Voice agent.
4. In the Twilio number's Voice configuration, set the incoming-call webhook to:

   `https://<public-api-host>/api/v1/telephony/twilio/incoming-call`

   Use HTTP POST.
5. The webhook validates `X-Twilio-Signature`, creates TwiML with a signed WSS stream, and passes the called number, caller number and Twilio Call SID to the media-stream handler.

## Runtime behavior

- The called DID is resolved to an active tenant and a published tenant agent.
- The system prompt is built from the existing tenant Knowledge Base, live tenant data, tenant policy and agent instructions.
- Deepgram Nova-2 transcribes the 8 kHz G.711 mu-law phone stream.
- OpenAI Chat Completions handles the spoken turn and function calls.
- Deepgram Aura returns 8 kHz mu-law audio to Twilio.
- Caller identity, callback leads, reception alerts, transcript, call status and duration are saved in the existing tenant CRM/call tables.
- Callback notifications and completed-call summaries use the platform's configured email and WhatsApp notification channels.
- WhatsApp information is sent to the verified caller only after an explicit request.

## Important scope limits — not production sign-off

This commit implements the Twilio Media Streams path only. It does **not** implement Exotel's provider-specific stream protocol, live SIP registration/provisioning, or audio-file recording/storage. The existing SIP trunk screens currently store trunk/DID configuration; the Twilio adapter uses DID routing and Twilio's Media Streams webhook, not SIP REGISTER. Call transcripts and metadata are persisted, but raw audio recordings are not yet persisted.

The current Deepgram configuration uses Nova-2 with `en-IN` and Aura English output. Sarvam AI and multilingual TTS selection are not yet wired into this adapter. Live provider credentials and a real Twilio DID are required for an end-to-end call test.
