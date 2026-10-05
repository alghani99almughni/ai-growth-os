# AI Growth OS — Web Call Runtime

Browser-first, app-like calling layer for tenant websites/PWAs.

## Locked flow

Customer website/PWA -> Call AI -> Web Call Runtime -> Call Session Manager -> secure signaling -> WebRTC -> STUN/TURN fallback -> AI Voice Gateway -> Knowledge/CRM/Booking.

## Customer experience

- App-like call layer over the existing webpage.
- Full call panel with connected state, timer, mute, audio controls and end.
- Minimize to floating call bubble while the webpage remains available.
- Live transcription.
- Customer note/chat input below transcription; notes stay in the same AI call context.
- Warn before leaving while an active call exists where browser support allows.
- Browser closure is treated as disconnect.

## Reliability

- Authenticated WSS signaling.
- WebRTC ICE monitoring.
- Direct ICE, TURN UDP, TURN TCP, TURN TLS/443 fallback.
- Network change detection.
- ICE restart and reconnect.
- Audio-quality watchdog.
- Session watchdog and structured call events.
- Technical failure is not misclassified as customer silence.

## Customer responsiveness

Default no-response timeout: 60 seconds. The system distinguishes genuine customer silence from technical audio/network failure. Genuine silence can receive a configurable prompt; after the configured terminal timeout the call ends.

## Automatic callback

If the call becomes unclear/unusable because of technical or connection issues and recovery cannot restore acceptable quality, create a callback workflow automatically using the customer number already captured at call start.

Callback record keeps the original call/session IDs, failure reason, diagnostics and status.

## Tenant backend

Tenant/Super Admin requires call monitoring, presence, session lifecycle, signaling health, WebRTC/ICE/TURN diagnostics, AI gateway health, transcript, customer notes, call metrics, reconnect history, outcomes and callback workflow.

## Native Android alignment

Android is an optional native client using the same Call Gateway, call session model, signaling protocol, TURN strategy, AI gateway and CRM. Native background/lock-screen capabilities remain Android-only.

## Rollout

The Web Call Runtime must remain on a separate route until local tests, browser WebRTC tests, backend signaling, TURN, AI audio, recovery, 60-second behavior, customer notes, callback automation and tenant isolation all pass. Only then replace the current production Call button target.