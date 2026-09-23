# AI Growth OS — Error Log

## ERR-2026-09-23-001 — SS Nutritions PWA AI call failed during realtime connection

- **Date:** 2026-09-23
- **Product area:** SS Nutritions PWA / Public Voice
- **Environment:** Production (Render)
- **Severity:** High — customer could submit name/mobile but could not establish the AI voice session
- **Status:** Fix deployed/in deployment; final browser verification pending

### Customer-visible symptom
After entering the customer's name and mobile number and pressing **Start call**, the UI displayed:

> The AI call connection failed. Please try again.

The AI did not greet the customer and the conversation never started.

### Expected behavior
1. Customer enters name and mobile number.
2. API creates the call session.
3. Realtime voice WebSocket authenticates successfully.
4. AI greets the customer first using the verified name.
5. Customer can speak naturally and receive realtime responses.

### Observed technical behavior
- The call creation request successfully created a call session.
- The failure occurred when the browser attempted to establish the realtime public voice WebSocket.
- The WebSocket authentication path rejected the public call-room token, so the AI voice session never reached the provider/greeting stage.

### Root cause
The public realtime voice room was using JWT-based room authentication directly through the browser WebSocket query-string flow. In production, this authentication exchange was not reliably surviving the WebSocket/proxy path, resulting in rejection before the realtime voice gateway could start.

### Fix
Commit: `29d2ccc6bb498a4b1d226e685f6b5b17009daa6f`

Changed public call-room authentication to a short-lived, URL-safe, HMAC-SHA256 signed token dedicated to the call session.

Security properties:
- Bound to the specific `call_id`
- Bound to the specific audience (`call-ai` or `call-customer`)
- Expires after 10 minutes
- Signature verified server-side with the application's JWT secret
- Uses constant-time signature comparison

### Regression checks required
- [ ] Production API deployment becomes Live
- [ ] Start call from SS Nutritions PWA
- [ ] WebSocket connects without 403
- [ ] AI greets the customer first
- [ ] Customer question receives realtime response
- [ ] Transcript is persisted to CRM
- [ ] Call duration/status is persisted
- [ ] Knowledge-first response is used where applicable
- [ ] Human callback path remains available when escalation is required

### Related fixes
- Realtime AI made the primary SS Nutritions call path.
- Verified customer identity is passed into the voice agent so the AI does not ask for name/mobile again.


## ERR-2026-09-23-002 — Public voice WebSocket continued returning 403 after token fix

- **Date:** 2026-09-23
- **Product area:** SS Nutritions PWA / Public Voice
- **Environment:** Production (Render)
- **Severity:** High
- **Status:** New architecture fix deployed/pending final browser verification

### Customer-visible symptom
The call UI briefly showed **Connecting**, then returned to the error state:
> The AI call connection failed. Please try again.

The customer identity form itself was accepted.

### Production evidence
Render recorded successful call creation:
- `POST /api/v1/public/business/ss-nutritions/call` → `201 Created`

Immediately afterward the realtime connection was rejected:
- `WebSocket /ws/public/voice/{call_id}` → `403`
- `connection rejected (403 Forbidden)`

This occurred repeatedly during the test session.

### Diagnosis
The previous short-lived HMAC room-token approach still depended on a query-string authentication exchange for the public AI WebSocket. Although the call token was being generated, the production connection was still being rejected before the voice handler could start. Therefore the failure remained in the public WebSocket admission layer, before realtime AI processing.

### Corrective architecture
The public AI leg is now bound directly to the server-created **CallRecord**:
- browser connects using the opaque server-generated UUID call ID
- server requires `source == pwa_voice`
- server requires status `ringing` or `connected`
- server requires the call to have started within 10 minutes
- no browser-supplied JWT/HMAC query token is required for the AI WebSocket
- the call record remains the authorization boundary

The frontend now connects to `/ws/public/voice/{call_id}`.

### Code changes
- API: commit `0c06ec6a11948e21593cd779a59499cac060864b`
- Web: commit `affbe6ac7c4417491e923882e717ef3a1ffcde1b`

### Regression checklist
- [ ] API deployment live
- [ ] Web deployment live
- [ ] Call POST returns 201
- [ ] WebSocket reaches handler without 403
- [ ] AI realtime provider connects
- [ ] AI greets customer first
- [ ] Customer can speak
- [ ] AI response audio is heard
- [ ] Transcript is persisted
- [ ] Call status/duration is persisted
- [ ] Knowledge-first routing works


## ERR-2026-09-23-003 — Session-bound WebSocket still surfaced as HTTP 403

- **Date:** 2026-09-23
- **Product area:** SS Nutritions PWA / Public Voice
- **Environment:** Production (Render)
- **Severity:** High
- **Status:** Diagnostic fix deployed/pending browser verification

### Customer-visible symptom
The UI showed **Connecting** and then returned to the AI call connection error.

### Production evidence
After the session-bound WebSocket deployment was Live, production still recorded:
- POST /api/v1/public/business/ss-nutritions/call → 201 Created
- WebSocket /ws/public/voice/{call_id} → 403
- connection rejected (403 Forbidden)

### Important diagnosis
The HTTP/WebSocket server reports a 403 whenever the application closes the WebSocket before accepting the handshake. Therefore the 403 does not by itself prove that Render or the browser is blocking the WebSocket. The application was able to reach the route but could be rejecting the call during pre-accept validation.

### Corrective diagnostic change
The voice WebSocket now accepts the handshake first and performs call-session validation immediately afterward. Invalid sessions receive an application-level WebSocket error/close code instead of an HTTP 403.

This exposes the actual failure reason to the browser and production logs and avoids another blind authentication-layer patch.

### Next regression checks
- [ ] Deployment Live
- [ ] WebSocket handshake no longer returns HTTP 403
- [ ] If session validation fails, browser receives call_not_found or call_not_active
- [ ] If validation passes, realtime provider connects
- [ ] AI greeting is heard
- [ ] Customer speech receives AI response
