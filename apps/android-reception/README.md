# AI Growth OS — Kotlin Reception WebRTC

Standalone Android staff/reception companion for the main AI Growth OS project.

It signs into the existing FastAPI API, polls the tenant call queue, accepts/declines handoffs, and uses a real org.webrtc PeerConnection. SDP and ICE are relayed through the authenticated /ws/calls/{call_id} room; media is peer-to-peer. STUN is supported and the existing /voice/ice endpoint can return TURN credentials.

The supplied Aura WebRTC classes were inspected as the architectural reference, but their SDP/audio implementation was simulated. This module uses the real WebRTC Android SDK instead.

Open this folder as a standalone Android Studio project and point API URL at the deployed API.
