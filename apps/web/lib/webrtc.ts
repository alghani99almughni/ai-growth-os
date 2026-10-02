"use client";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const wsBase = () => api().replace(/^http:/, "ws:").replace(/^https:/, "wss:");

const ICE_SERVERS: RTCIceServer[] = [
    { urls: "stun:stun.l.google.com:19302" },
    { urls: "stun:stun1.l.google.com:19302" },
];

export type HumanConnection = {
    peer: RTCPeerConnection;
    socket: WebSocket;
    close: () => void;
};

/**
 * Connect a customer browser to a staff browser over WebRTC, using the same
 * signalling WebSocket the staff side uses (/ws/calls/{call_id}?room_token=…).
 * Returns a handle the modal can keep in a ref and .close() on teardown.
 */
export async function connectCustomerToStaff(
    apiBase: string,
    _slug: string,
    callId: string,
    roomToken: string,
    micStream: MediaStream,
): Promise<HumanConnection> {
    const peer = new RTCPeerConnection({ iceServers: ICE_SERVERS });
    micStream.getTracks().forEach(track => peer.addTrack(track, micStream));

    const audio = new Audio();
    audio.autoplay = true;
    audio.setAttribute("playsinline", "true");
    peer.ontrack = event => {
        audio.srcObject = event.streams[0] || new MediaStream([event.track]);
        audio.play().catch(() => {});
    };

    const ws = new WebSocket(
        wsBase() + "/ws/calls/" + encodeURIComponent(callId) +
        "?room_token=" + encodeURIComponent(roomToken)
    );

    const pendingCandidates: RTCIceCandidateInit[] = [];
    let remoteReady = false;

    peer.onicecandidate = event => {
        if (event.candidate && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: "signal",
                data: { candidate: event.candidate.toJSON() },
            }));
        }
    };

    await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(
            () => reject(new Error("Human call signaling timed out.")),
            15000
        );
        ws.onopen = () => {
            window.clearTimeout(timeout);
            ws.send(JSON.stringify({ type: "join", role: "customer" }));
            resolve();
        };
        ws.onerror = () => {
            window.clearTimeout(timeout);
            reject(new Error("Human call signaling connection failed."));
        };
    });

    ws.onmessage = async event => {
        let message: any;
        try { message = JSON.parse(event.data); } catch { return; }

        const { sdp, candidate } = message.data || {};
        if (sdp) {
            await peer.setRemoteDescription(sdp);
            remoteReady = true;
            if (sdp.type === "offer") {
                const answer = await peer.createAnswer();
                await peer.setLocalDescription(answer);
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        type: "signal",
                        data: { sdp: peer.localDescription?.toJSON() },
                    }));
                }
            }
            for (const c of pendingCandidates.splice(0)) {
                await peer.addIceCandidate(c).catch(() => {});
            }
            return;
        }
        if (candidate) {
            if (remoteReady) await peer.addIceCandidate(candidate).catch(() => {});
            else pendingCandidates.push(candidate);
        }
        if (message.type === "ended") {
            try { peer.close(); } catch {}
            try { ws.close(); } catch {}
        }
    };

    peer.onconnectionstatechange = () => {
        if (peer.connectionState === "failed" || peer.connectionState === "closed") {
            try { ws.close(); } catch {}
        }
    };

    return {
        peer,
        socket: ws,
        close: () => {
            try { ws.send(JSON.stringify({ type: "hangup" })); } catch {}
            try { ws.close(); } catch {}
            try { peer.close(); } catch {}
            audio.srcObject = null;
        },
    };
}