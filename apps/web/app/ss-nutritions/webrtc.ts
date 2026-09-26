export type HumanWebRtcConnection = {
  peer: RTCPeerConnection;
  socket: WebSocket;
  close: () => void;
};

function wsBase(apiBase: string) {
  return apiBase.replace(/^https:/, "wss:").replace(/^http:/, "ws:").replace(/\/$/, "");
}

export async function connectCustomerToStaff(
  apiBase: string,
  callId: string,
  roomToken: string,
  localStream: MediaStream
): Promise<HumanWebRtcConnection> {
  const iceResponse = await fetch(
    apiBase + "/api/v1/public/business/ss-nutritions/voice/ice",
    { cache: "no-store" }
  );
  const icePayload = await iceResponse.json();
  const peer = new RTCPeerConnection({
    iceServers: icePayload.ice_servers || [{ urls: "stun:stun.l.google.com:19302" }]
  });

  localStream.getTracks().forEach((track) => peer.addTrack(track, localStream));

  const remoteAudio = new Audio();
  remoteAudio.autoplay = true;
  remoteAudio.setAttribute("playsinline", "true");
  peer.ontrack = (event) => {
    if (event.streams[0]) remoteAudio.srcObject = event.streams[0];
    else remoteAudio.srcObject = new MediaStream([event.track]);
    remoteAudio.play().catch(() => {});
  };

  const socket = new WebSocket(
    wsBase(apiBase) + "/ws/calls/" + encodeURIComponent(callId) +
    "?room_token=" + encodeURIComponent(roomToken)
  );

  const pendingCandidates: RTCIceCandidateInit[] = [];
  let remoteDescriptionReady = false;

  peer.onicecandidate = (event) => {
    if (!event.candidate || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({
      type: "ice-candidate",
      candidate: {
        sdpMid: event.candidate.sdpMid,
        sdpMLineIndex: event.candidate.sdpMLineIndex,
        candidate: event.candidate.candidate
      }
    }));
  };

  const opened = new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("Human call signaling timed out.")), 15000);
    socket.onopen = () => {
      window.clearTimeout(timer);
      resolve();
    };
    socket.onerror = () => {
      window.clearTimeout(timer);
      reject(new Error("Human call signaling connection failed."));
    };
  });

  socket.onmessage = async (event) => {
    try {
      const message = JSON.parse(event.data);
      if (message.type === "offer") {
        await peer.setRemoteDescription({ type: "offer", sdp: message.sdp });
        remoteDescriptionReady = true;
        for (const candidate of pendingCandidates.splice(0)) {
          await peer.addIceCandidate(candidate).catch(() => {});
        }
        const answer = await peer.createAnswer();
        await peer.setLocalDescription(answer);
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({
            type: "answer",
            sdp: answer.sdp
          }));
        }
      } else if (message.type === "ice-candidate") {
        const candidate = message.candidate || message;
        if (!remoteDescriptionReady) pendingCandidates.push(candidate);
        else await peer.addIceCandidate(candidate).catch(() => {});
      } else if (message.type === "hangup" || message.type === "stop") {
        peer.close();
      }
    } catch {
      // Ignore malformed signaling frames; the call state remains controlled by the peer connection.
    }
  };

  peer.onconnectionstatechange = () => {
    if (peer.connectionState === "failed" || peer.connectionState === "closed") {
      try { socket.close(); } catch {}
    }
  };

  await opened;

  return {
    peer,
    socket,
    close: () => {
      try { socket.send(JSON.stringify({ type: "hangup" })); } catch {}
      try { socket.close(); } catch {}
      try { peer.close(); } catch {}
      remoteAudio.srcObject = null;
    }
  };
}
