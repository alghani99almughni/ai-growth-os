"""
WebSocket voice bridge for the SS Nutritions AI widget.

The frontend opens:
    wss://<api-host>/ws/calls/{call_id}?room_token=<token>

Handshake contract (matches the widget's expectations):
    - Server sends  {"type": "offer",         "sdp": "..."}
    - Client sends  {"type": "answer",        "sdp": "..."}
    - Both send     {"type": "ice-candidate", "candidate": {...}}
    - Both send     {"type": "hangup"}

Audio path:
    - Incoming RTP audio  -> frames -> (optional STT)
    - (optional TTS)      -> audio frames -> outgoing RTP

If STT/TTS providers are not configured, the route still upgrades the
WebSocket and returns a valid SDP offer with silence, so the widget
does not spin in an error loop. Replace `generate_ai_reply_audio`
with your real STT/TTS pipeline when ready.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.mediastreams import MediaStreamTrack, MediaStreamError
from av import AudioFrame

logger = logging.getLogger("api.ws_voice")

router = APIRouter()


# ---------------------------------------------------------------------------
# Simple in-memory room token store. Replace with DB/Redis lookup as needed.
# ---------------------------------------------------------------------------
def _valid_room_token(call_id: str, room_token: str) -> bool:
    if not room_token:
        return False
    # TODO: look up the token issued by /handoff for this call_id
    # For now accept any non-empty token so the widget can connect.
    return True


# ---------------------------------------------------------------------------
# Audio track that emits silence. Replace the generator with your TTS.
# ---------------------------------------------------------------------------
class SilenceAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, sample_rate: int = 48000, frame_ms: int = 20):
        super().__init__()
        self.sample_rate = sample_rate
        self.samples_per_frame = int(sample_rate * frame_ms / 1000)
        self._pts = 0

    async def recv(self) -> AudioFrame:
        await asyncio.sleep(self.samples_per_frame / self.sample_rate)
        frame = AudioFrame(format="s16", layout="mono", samples=self.samples_per_frame)
        frame.sample_rate = self.sample_rate
        frame.pts = self._pts
        frame.time_base = None
        for plane in frame.planes:
            plane.update(b"\x00" * plane.buffer_size)
        self._pts += self.samples_per_frame
        return frame


async def _drain_incoming_audio(track) -> None:
    """Consume incoming customer audio so aiortc doesn't stall."""
    try:
        while True:
            await track.recv()
    except MediaStreamError:
        return
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("incoming audio loop crashed")
        return


# ---------------------------------------------------------------------------
# The WebSocket endpoint
# ---------------------------------------------------------------------------
@router.websocket("/ws/calls/{call_id}")
async def ws_calls(websocket: WebSocket, call_id: str) -> None:
    room_token = websocket.query_params.get("room_token", "")
    if not _valid_room_token(call_id, room_token):
        await websocket.close(code=4403)
        return

    await websocket.accept()
    logger.info("ws open call_id=%s", call_id)

    ice_servers_env = os.getenv("ICE_SERVERS_JSON", "").strip()
    if ice_servers_env:
        try:
            raw = json.loads(ice_servers_env)
            ice_servers = [RTCIceServer(**s) for s in raw]
        except Exception:
            ice_servers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]
    else:
        ice_servers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]

    pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=ice_servers))

    # Serve audio to the customer.
    pc.addTrack(SilenceAudioTrack())

    # Consume customer audio (so the connection actually stays alive).
    @pc.on("track")
    def on_track(track):
        if track.kind == "audio":
            asyncio.create_task(_drain_incoming_audio(track))

    @pc.on("connectionstatechange")
    async def on_state():
        logger.info("pc state=%s call_id=%s", pc.connectionState, call_id)
        if pc.connectionState in ("failed", "closed"):
            await websocket.close(code=1011)

    @pc.on("icecandidate")
    async def on_ice(candidate):
        if candidate is None:
            return
        try:
            await websocket.send_json({
                "type": "ice-candidate",
                "candidate": {
                    "sdpMid": candidate.sdpMid,
                    "sdpMLineIndex": candidate.sdpMLineIndex,
                    "candidate": candidate.candidate,
                },
            })
        except Exception:
            logger.exception("failed to send ice candidate")

    try:
        # 1) Server -> client offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        await websocket.send_json({
            "type": "offer",
            "sdp": pc.localDescription.sdp,
        })

        # 2) Client <-> server messages
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")

            if mtype == "answer":
                await pc.setRemoteDescription(
                    RTCSessionDescription(sdp=msg["sdp"], type="answer")
                )
            elif mtype == "ice-candidate":
                from aiortc import RTCIceCandidate
                cand = msg.get("candidate") or {}
                await pc.addIceCandidate(RTCIceCandidate(
                    sdpMid=cand.get("sdpMid"),
                    sdpMLineIndex=cand.get("sdpMLineIndex"),
                    candidate=cand.get("candidate", ""),
                ))
            elif mtype in ("hangup", "stop"):
                break
            else:
                logger.debug("ignoring message type=%s", mtype)

    except WebSocketDisconnect:
        logger.info("ws closed by client call_id=%s", call_id)
    except Exception:
        logger.exception("ws error call_id=%s", call_id)
    finally:
        try:
            await pc.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("ws cleanup done call_id=%s", call_id)