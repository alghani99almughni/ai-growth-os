"use client";

import { useEffect, useRef, useState } from "react";

type Line = { role: "customer" | "ai" | "system"; text: string };

const api = () => String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const wsBase = () => api().replace(/^http:/, "ws:").replace(/^https:/, "wss:");

export default function WebCallLab({ slug }: { slug: string }) {
  const [name, setName] = useState("Syed Shukur");
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState("ready");
  const [error, setError] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [metrics, setMetrics] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [forceRelay, setForceRelay] = useState(false);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pendingIceRef = useRef<RTCIceCandidateInit[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const iceRecoveryTimerRef = useRef<number | null>(null);
  const iceRecoveryAttemptedRef = useRef(false);

  const addLine = (role: Line["role"], text: string) => {
    if (!text?.trim()) return;
    setLines((x) => [...x, { role, text: text.trim() }]);
  };

  const cleanup = () => {
    try { wsRef.current?.send(JSON.stringify({ type: "hangup" })); } catch {}
    try { wsRef.current?.close(); } catch {}
    try { pcRef.current?.close(); } catch {}
    streamRef.current?.getTracks().forEach((t) => t.stop());
    wsRef.current = null;
    pcRef.current = null;
    streamRef.current = null;
    if (iceRecoveryTimerRef.current !== null) window.clearTimeout(iceRecoveryTimerRef.current);
    iceRecoveryTimerRef.current = null;
    iceRecoveryAttemptedRef.current = false;
    setRunning(false);
  };

  const start = async () => {
    if (running) return;
    setError("");
    setLines([]);
    setMetrics([]);
    setStatus("starting");
    pendingIceRef.current = [];

    try {
      if (!name.trim() || !phone.trim()) throw new Error("Enter name and mobile number first.");

      const startRes = await fetch(`${api()}/api/v1/public/business/${encodeURIComponent(slug)}/call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), phone: phone.trim() }),
      });
      const startData = await startRes.json().catch(() => ({}));
      if (!startRes.ok) throw new Error(startData.detail || "Could not start call.");

      const iceRes = await fetch(`${api()}/api/v1/public/business/${encodeURIComponent(slug)}/voice/ice`, { cache: "no-store" });
      const iceData = await iceRes.json().catch(() => ({}));

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;

      const pc = new RTCPeerConnection({
        iceServers: iceData.ice_servers || [{ urls: "stun:stun.l.google.com:19302" }],
        ...(forceRelay ? { iceTransportPolicy: "relay" as RTCIceTransportPolicy } : {}),
      });
      pcRef.current = pc;
      stream.getTracks().forEach((track) => pc.addTrack(track, stream));

      const turnAvailable = (iceData.ice_servers || []).some((server: { urls?: string | string[] }) =>
        (Array.isArray(server.urls) ? server.urls : [server.urls]).some((url) => String(url || "").toLowerCase().startsWith("turn:") || String(url || "").toLowerCase().startsWith("turns:"))
      );
      const recoverIce = () => {
        if (forceRelay || iceRecoveryAttemptedRef.current || !turnAvailable || pc.connectionState === "connected") return;
        iceRecoveryAttemptedRef.current = true;
        setMetrics((x) => [...x, "ice_recovery=forcing_turn_relay"]);
        try {
          pc.setConfiguration({ iceServers: iceData.ice_servers, iceTransportPolicy: "relay" });
          pc.restartIce();
        } catch {
          setMetrics((x) => [...x, "ice_recovery=failed"]);
        }
      };
      const scheduleIceRecovery = () => {
        if (iceRecoveryTimerRef.current !== null || forceRelay || iceRecoveryAttemptedRef.current) return;
        iceRecoveryTimerRef.current = window.setTimeout(() => {
          iceRecoveryTimerRef.current = null;
          recoverIce();
        }, 5000);
      };

      pc.ontrack = (event) => {
        const remote = event.streams[0] || new MediaStream([event.track]);
        if (audioRef.current) {
          audioRef.current.srcObject = remote;
          void audioRef.current.play().catch(() => {});
        }
      };
      pc.onconnectionstatechange = () => {
        setStatus(`webrtc:${pc.connectionState}`);
        setMetrics((x) => [...x, `pc=${pc.connectionState}`]);
        if (pc.connectionState === "connected") {
          if (iceRecoveryTimerRef.current !== null) window.clearTimeout(iceRecoveryTimerRef.current);
          iceRecoveryTimerRef.current = null;
        } else if (pc.connectionState === "disconnected") {
          scheduleIceRecovery();
        } else if (pc.connectionState === "failed") {
          recoverIce();
        }
      };
      pc.oniceconnectionstatechange = () => {
        setStatus(`ice:${pc.iceConnectionState}`);
        setMetrics((x) => [...x, `ice=${pc.iceConnectionState}`]);
        if (pc.iceConnectionState === "checking") scheduleIceRecovery();
        if (pc.iceConnectionState === "failed") recoverIce();
      };
      pc.onicegatheringstatechange = () => {
        setMetrics((x) => [...x, `ice_gathering=${pc.iceGatheringState}`]);
      };

      const ws = new WebSocket(
        `${wsBase()}/ws/public/webcall/${encodeURIComponent(startData.call_id)}?room_token=${encodeURIComponent(startData.room_token)}`
      );
      wsRef.current = ws;

      const sendIce = (candidate: RTCIceCandidateInit) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "ice-candidate", candidate }));
        } else {
          pendingIceRef.current.push(candidate);
        }
      };

      pc.onicecandidate = (event) => {
        if (!event.candidate) return;
        sendIce({
          candidate: event.candidate.candidate,
          sdpMid: event.candidate.sdpMid,
          sdpMLineIndex: event.candidate.sdpMLineIndex,
        });
      };

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);

      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error("Web Call signaling timed out.")), 15000);
        ws.onopen = () => {
          window.clearTimeout(timeout);
          // The server requires the SDP offer to be the first client message.
          // ICE candidates may have been gathered before the WebSocket opened,
          // so keep them queued until immediately after the offer is sent.
          resolve();
        };
        ws.onerror = () => {
          window.clearTimeout(timeout);
          reject(new Error("Web Call signaling failed."));
        };
      });

      ws.onmessage = async (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "answer") {
            await pc.setRemoteDescription({ type: "answer", sdp: msg.sdp });
            setRunning(true);
            setStatus("connected");
          } else if (msg.type === "transcript") {
            addLine(msg.role === "customer" ? "customer" : "ai", msg.text);
            if (msg.crosscheck) {
              setMetrics((x) => [
                ...x,
                `${msg.crosscheck.intent} · ${msg.crosscheck.confidence} · ${msg.crosscheck.latency_ms}ms`,
              ]);
            }
          } else if (msg.type === "status") {
            setStatus(msg.status || "active");
            if (msg.provider) setMetrics((x) => [...x, `provider=${msg.provider}`]);
          } else if (msg.type === "pc_state") {
            setStatus(`webrtc:${msg.state}`);
          } else if (msg.type === "interruption") {
            setMetrics((x) => [...x, "barge-in: AI audio interrupted"]);
          } else if (msg.type === "timeout") {
            addLine("system", "Customer inactivity timeout — call ended.");
            cleanup();
          } else if (msg.type === "error") {
            setError(msg.message || msg.code || "Web Call runtime error");
            cleanup();
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : "Invalid Web Call event.");
        }
      };

      // The server requires the SDP offer to be the first client message.
      ws.send(JSON.stringify({
        type: "offer",
        sdp: pc.localDescription?.sdp,
        sdp_type: pc.localDescription?.type || "offer",
      }));
      ws.send(JSON.stringify({
        type: "diagnostic",
        event: "client_ice_policy",
        force_relay: forceRelay,
      }));
      // Now that the required first message (offer) is on the wire, flush
      // any ICE candidates gathered while the WebSocket was opening.
      for (const candidate of pendingIceRef.current.splice(0)) sendIce(candidate);
      addLine("system", "WebRTC media session started.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Web Call failed.");
      setStatus("error");
      cleanup();
    }
  };

  useEffect(() => () => cleanup(), []);

  return (
    <main style={{ maxWidth: 1000, margin: "40px auto", padding: 24, fontFamily: "system-ui" }}>
      <h1>AI Growth OS — Web Call Runtime Lab</h1>
      <p>Dograh-inspired WebRTC media test. This does not replace the production Call button.</p>
      <div style={{ display: "grid", gap: 12, maxWidth: 520 }}>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Customer name" />
        <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Mobile number" />
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input type="checkbox" checked={forceRelay} onChange={(e) => setForceRelay(e.target.checked)} disabled={running} />
          Force TURN relay (diagnostic)
        </label>
        {!running ? <button onClick={start}>Start Web Call Test</button> : <button onClick={cleanup}>End Call</button>}
        <strong>Status: {status}</strong>
        {error && <div style={{ color: "crimson" }}>{error}</div>}
      </div>
      <audio ref={audioRef} autoPlay playsInline />
      <section style={{ marginTop: 24 }}>
        <h2>Live Transcript</h2>
        {lines.map((line, i) => <div key={i}><b>{line.role}:</b> {line.text}</div>)}
      </section>
      <section style={{ marginTop: 24 }}>
        <h2>Runtime Diagnostics</h2>
        {metrics.map((m, i) => <div key={i}>{m}</div>)}
      </section>
    </main>
  );
}
