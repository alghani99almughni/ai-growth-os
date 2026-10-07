# Web Call Runtime Lab

## Purpose

This is an isolated Dograh-inspired WebRTC media runtime for AI Growth OS. It does not replace the production customer Call button.

## Local API

From the repository root:

1. Start the API on port 8000 using the existing project environment.
2. Confirm `http://localhost:8000/health`.
3. Confirm the API has the same Gemini/OpenAI realtime credentials used by the existing voice runtime.
4. Start the web app on its normal development port.

## Test URL

Open:

`http://localhost:3000/webcall-lab/<tenant-slug>`

For SS Nutritions, use the tenant slug already present in the local database.

## Test sequence

1. Enter customer name and mobile number.
2. Click **Start Web Call Test**.
3. Allow microphone access.
4. Wait for `connected`.
5. Confirm the AI greeting is audible.
6. Ask a normal business question.
7. Interrupt the AI while it is speaking and verify the old audio stops.
8. Ask another question and verify a new response arrives.
9. Watch Runtime Diagnostics for provider and Knowledge Brain V2 cross-check data.
10. Stay silent for 60 seconds and verify the runtime ends the call.
11. Click End Call and confirm the microphone and WebRTC session stop.

## Failure evidence to capture

If the call fails, capture:

- browser Console
- browser Network -> WS messages for `/ws/public/webcall/`
- API terminal/Render logs containing `WEB_CALL_`
- WebRTC connection state
- ICE connection state
- provider name
- exact timestamp

Do not change the production Call button while this lab is being tested.

## Next gate

Local browser call must pass before the branch is deployed to a separate Render staging Web/API environment.
