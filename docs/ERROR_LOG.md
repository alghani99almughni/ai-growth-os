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
