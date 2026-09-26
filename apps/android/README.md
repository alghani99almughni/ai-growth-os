# AI Growth OS Android Reception WebRTC

This module ports the Aura Reception AI WebRTC session/signaling architecture into the current AI Growth OS repository.

Aura's uploaded project contains a proven session/state layer, but its WebRtcAudioStreamService generates synthetic frames for UI/logic testing and does not include a native WebRTC SDK. This module keeps the Aura lifecycle while using a real native Android WebRTC PeerConnection.

The Android client connects to the current FastAPI call room:
wss://API_HOST/ws/calls/CALL_ID?access_token=STAFF_JWT

The backend already authenticates the staff JWT against the tenant and assigned staff member. The client sends staff_join after the WebSocket opens, exchanges SDP/ICE, and exposes mute, hold, and hangup controls.

Integration:
1. Authenticate a reception staff member and obtain the existing tenant JWT.
2. Obtain the active call_id.
3. Call startIncomingCall(callId, tenantId, callerName, accessToken, apiBaseUrl).
4. Call acceptCall() when the receptionist answers.
5. Use toggleMute(), toggleHold(), and endCall() from the reception UI.

The Android module is isolated under apps/android, so the existing Render FastAPI/Next.js services are not changed by this module.
