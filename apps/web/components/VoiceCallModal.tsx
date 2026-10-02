"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { connectCustomerToStaff } from "../app/ss-nutritions/webrtc";

const API = () =>
    String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const WS_API = () => API().replace(/^http:/, "ws:").replace(/^https:/, "wss:");

type Props = {
    slug: string;
    businessName: string;
    agentGender?: "female" | "male";
    onClose: () => void;
};

type CallState = "idle" | "starting" | "connecting" | "connected" | "ended" | "error";
type TranscriptItem = { role: "ai" | "customer"; text: string };

const HOLD_LINES: Record<string, string> = {
    en: "Please hold on while we connect you to the right executive.",
    hi: "कृपया प्रतीक्षा करें, हम आपको हमारी टीम से जोड़ रहे हैं।",
    te: "దయచేసి వేచి ఉండండి, మేము మిమ్మల్ని మా టీమ్‌కు కనెక్ట్ చేస్తున్నాము.",
    ta: "தயவுசெய்து காத்திருங்கள், நாங்கள் உங்களை எங்கள் குழுவுடன் இணைக்கிறோம்.",
    kn: "ದಯವಿಟ್ಟು ನಿರೀಕ್ಷಿಸಿ, ನಾವು ನಿಮ್ಮನ್ನು ನಮ್ಮ ತಂಡಕ್ಕೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇವೆ.",
    ml: "ദയവായി കാത്തിരിക്കുക, ഞങ്ങൾ നിങ്ങളെ ഞങ്ങളുടെ ടീമുമായി ബന്ധിപ്പിക്കുന്നു.",
    mr: "कृपया थांबा, आम्ही तुम्हाला आमच्या टीमशी जोडत आहोत.",
    bn: "অনুগ্রহ করে অপেক্ষা করুন, আমরা আপনাকে আমাদের দলের সাথে সংযুক্ত করছি।",
    gu: "કૃપા કરીને રાહ જુઓ, અમે તમને અમારી ટીમ સાથે જોડી રહ્યા છીએ.",
    pa: "ਕਿਰਪਾ ਕਰਕੇ ਉਡੀਕ ਕਰੋ, ਅਸੀਂ ਤੁਹਾਨੂੰ ਸਾਡੀ ਟੀਮ ਨਾਲ ਜੋੜ ਰਹੇ ਹਾਂ।",
    ur: "براہ کرم انتظار کریں، ہم آپ کو ہماری ٹیم سے جوڑ رہے ہیں۔",
};

export default function VoiceCallModal({ slug, businessName, onClose }: Props) {
    const [callState, setCallState] = useState<CallState>("idle");
    const [name, setName] = useState("");
    const [phone, setPhone] = useState("");
    const [callError, setCallError] = useState("");
    const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
    const [muted, setMuted] = useState(false);
    const [layer, setLayer] = useState<"brain" | "gemini" | "human">("brain");

    const callActiveRef = useRef(false);
    const mutedRef = useRef(false);
    const callIdRef = useRef<string | null>(null);
    const socketRef = useRef<WebSocket | null>(null);
    const micRef = useRef<MediaStream | null>(null);
    const audioCtxRef = useRef<AudioContext | null>(null);
    const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
    const processorRef = useRef<ScriptProcessorNode | null>(null);
    const playbackQueueRef = useRef<Float32Array<ArrayBuffer>[]>([]);
    const playingRef = useRef(false);
    const humanConnectionRef = useRef<any>(null);
    const wakeLockRef = useRef<any>(null);

    const appendTranscript = useCallback((role: "ai" | "customer", text: string) => {
        const value = String(text || "").trim();
        if (!value) return;
        setTranscript(prev => {
            const last = prev[prev.length - 1];
            if (last && last.role === role && last.text === value) return prev;
            return [...prev, { role, text: value }];
        });
    }, []);

    const playPcm = useCallback(async (base64: string, sampleRate = 24000) => {
        const ctx = audioCtxRef.current;
        if (!ctx || !base64) return;
        if (ctx.state === "suspended") await ctx.resume();

        const raw = atob(base64);
        const bytes = Uint8Array.from(raw, c => c.charCodeAt(0));
        const view = new DataView(bytes.buffer);
        const samples = new Float32Array(Math.floor(bytes.byteLength / 2));
        for (let i = 0; i < samples.length; i++) {
            samples[i] = view.getInt16(i * 2, true) / 32768;
        }
        playbackQueueRef.current.push(samples);
        if (playingRef.current) return;

        playingRef.current = true;
        try {
            while (playbackQueueRef.current.length && callActiveRef.current) {
                const chunk = playbackQueueRef.current.shift();
                if (!chunk) continue;
                const buffer = ctx.createBuffer(1, chunk.length, sampleRate);
                buffer.copyToChannel(chunk as Float32Array<ArrayBuffer>, 0);
                const source = ctx.createBufferSource();
                source.buffer = buffer;
                source.connect(ctx.destination);
                await new Promise<void>(resolve => {
                    source.onended = () => resolve();
                    source.start();
                });
            }
        } finally {
            playingRef.current = false;
        }
    }, []);

    const speakHoldLine = useCallback(async (language: string) => {
        const text = HOLD_LINES[language] || HOLD_LINES.en;
        appendTranscript("ai", text);
        if (!("speechSynthesis" in window)) return;
        try {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = language === "en" ? "en-IN" : language;
            await new Promise<void>(resolve => {
                utterance.onend = () => resolve();
                utterance.onerror = () => resolve();
                window.speechSynthesis.speak(utterance);
                setTimeout(resolve, 4000);
            });
        } catch {}
    }, [appendTranscript]);

    const teardown = useCallback(() => {
        try { socketRef.current?.close(); } catch {}
        socketRef.current = null;
        try { processorRef.current?.disconnect(); } catch {}
        processorRef.current = null;
        try { sourceRef.current?.disconnect(); } catch {}
        sourceRef.current = null;
        try { micRef.current?.getTracks().forEach(t => t.stop()); } catch {}
        micRef.current = null;
        try { audioCtxRef.current?.close(); } catch {}
        audioCtxRef.current = null;
        playbackQueueRef.current = [];
        playingRef.current = false;
        try { humanConnectionRef.current?.close(); } catch {}
        humanConnectionRef.current = null;
        try { wakeLockRef.current?.release?.(); } catch {}
        wakeLockRef.current = null;
    }, []);

    const endCall = useCallback(() => {
        callActiveRef.current = false;
        try {
            if (socketRef.current?.readyState === WebSocket.OPEN) {
                socketRef.current.send(JSON.stringify({ type: "stop" }));
            }
        } catch {}
        teardown();
        setCallState("ended");
    }, [teardown]);

    // ------------------------------------------------------------------
    // Layer 3 — Human handoff (unchanged from your current file)
    // ------------------------------------------------------------------
    const handoffToHuman = useCallback(async () => {
        const callId = callIdRef.current;
        if (!callId || !callActiveRef.current) return;

        try {
            setLayer("human");
            setCallState("connecting");
            setCallError("Connecting you to our team…");
            try { socketRef.current?.send(JSON.stringify({ type: "stop" })); } catch {}
            try { socketRef.current?.close(); } catch {}
            socketRef.current = null;

            const response = await fetch(
                API() + "/api/v1/public/business/" +
                encodeURIComponent(slug) + "/call/" +
                encodeURIComponent(callId) + "/handoff",
                { method: "POST" }
            );
            const activation = await response.json();
            if (!response.ok) throw new Error(activation.detail || "Human handoff is unavailable.");
            if (activation.status === "handoff_unavailable") {
                throw new Error("No team member is available right now.");
            }

            let roomToken = activation.room_token || "";
            for (let attempt = 0; attempt < 90 && callActiveRef.current; attempt++) {
                if (roomToken) {
                    const stream = await navigator.mediaDevices.getUserMedia({
                        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
                    });
                    humanConnectionRef.current = await connectCustomerToStaff(
                        API(), slug, callId, roomToken, stream
                    );
                    setCallState("connected");
                    setCallError("Connected to our team.");
                    return;
                }
                await new Promise(resolve => setTimeout(resolve, 1000));
                const statusResponse = await fetch(
                    API() + "/api/v1/public/business/" +
                    encodeURIComponent(slug) + "/call/" +
                    encodeURIComponent(callId) + "/handoff",
                    { cache: "no-store" }
                );
                if (statusResponse.ok) {
                    const status = await statusResponse.json();
                    roomToken = status.room_token || "";
                    if (status.status === "handoff_unavailable") {
                        throw new Error("No team member is available right now.");
                    }
                }
            }
            throw new Error("The team did not answer in time.");
        } catch (error: any) {
            setCallError(error?.message || "Human handoff failed.");
            setCallState("ended");
            callActiveRef.current = false;
            teardown();
        }
    }, [slug, teardown]);

    // ------------------------------------------------------------------
    // Mic + AudioContext used by both Layer 1 (/ws/public/voice) and Layer 2 (/ws/escalate)
    // ------------------------------------------------------------------
    const prepareMic = useCallback(async (ws: WebSocket) => {
        const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
        audioCtxRef.current = ctx;
        await ctx.resume();

        const mic = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            },
        });
        micRef.current = mic;

        const source = ctx.createMediaStreamSource(mic);
        sourceRef.current = source;

        const processor = ctx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;
        const ratio = ctx.sampleRate / 16000;

        processor.onaudioprocess = event => {
            if (mutedRef.current || ws.readyState !== WebSocket.OPEN || !callActiveRef.current) return;
            const input = event.inputBuffer.getChannelData(0);
            const outputLength = Math.max(1, Math.round(input.length / ratio));
            const pcm = new Int16Array(outputLength);
            for (let i = 0; i < outputLength; i++) {
                const sample = Math.max(-1, Math.min(1, input[Math.min(input.length - 1, Math.floor(i * ratio))]));
                pcm[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
            }
            const bytes = new Uint8Array(pcm.buffer);
            let binary = "";
            const chunkSize = 32768;
            for (let i = 0; i < bytes.length; i += chunkSize) {
                binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + chunkSize, bytes.length)));
            }
            try { ws.send(JSON.stringify({ type: "audio", data: btoa(binary) })); } catch {}
        };

        source.connect(processor);
        processor.connect(ctx.destination);
    }, []);

    // ------------------------------------------------------------------
    // Layer 2 — Gemini Live escalation
    // ------------------------------------------------------------------
    const escalateToGemini = useCallback(async (language: string): Promise<"ok" | "fallback"> => {
        const callId = callIdRef.current;
        if (!callId || !callActiveRef.current) return "fallback";

        // Tell the server we're escalating; it will look up the call + tenant.
        try {
            await fetch(
                API() + "/api/v1/public/business/" + encodeURIComponent(slug) +
                "/voice/escalate/hold-line?language=" + encodeURIComponent(language),
                { cache: "no-store" }
            );
        } catch {}

        const ws = new WebSocket(WS_API() + "/ws/escalate/" + encodeURIComponent(callId));
        socketRef.current = ws;

        try {
            await prepareMic(ws);
        } catch (err: any) {
            try { ws.close(); } catch {}
            return "fallback";
        }

        const opened = await new Promise<boolean>(resolve => {
            const timeout = window.setTimeout(() => resolve(false), 12000);
            ws.onopen = () => { window.clearTimeout(timeout); resolve(true); };
            ws.onerror = () => { window.clearTimeout(timeout); resolve(false); };
            ws.onclose = () => { window.clearTimeout(timeout); resolve(false); };
        });
        if (!opened) return "fallback";

        setLayer("gemini");
        setCallState("connected");
        setCallError("Connected to our team.");

        // Greet via text so Gemini starts speaking immediately.
        try {
            ws.send(JSON.stringify({ type: "text", text: "The customer has been handed over to you. Greet them warmly and continue the conversation." }));
        } catch {}

        return await new Promise<"ok" | "fallback">(resolve => {
            let settled = false;
            const finish = (result: "ok" | "fallback") => {
                if (settled) return;
                settled = true;
                resolve(result);
            };

            ws.onmessage = async event => {
                try {
                    const message = JSON.parse(event.data);

                    if (message.type === "status") {
                        if (message.status === "connected") {
                            setCallError("");
                        }
                        if (message.status === "ended") {
                            finish(callActiveRef.current ? "fallback" : "ok");
                        }
                        return;
                    }

                    if (message.type === "transcript") {
                        appendTranscript(
                            message.role === "customer" ? "customer" : "ai",
                            message.text
                        );
                        return;
                    }

                    if (message.type === "audio") {
                        await playPcm(message.data, message.sample_rate || 24000);
                        return;
                    }

                    if (message.type === "error") {
                        // Server told us Gemini isn't available → Layer 3.
                        finish("fallback");
                        return;
                    }
                } catch {}
            };

            ws.onclose = () => {
                if (!callActiveRef.current) { finish("ok"); return; }
                finish("fallback");
            };

            ws.onerror = () => finish("fallback");
        });
    }, [slug, appendTranscript, playPcm, prepareMic]);

    // ------------------------------------------------------------------
    // Layer 1 — Deterministic brain WebSocket (unchanged)
    // ------------------------------------------------------------------
    const openVoiceWebSocket = useCallback(async (callId: string) => {
        const ws = new WebSocket(
            WS_API() + "/ws/public/voice/" + encodeURIComponent(callId)
        );
        socketRef.current = ws;

        await prepareMic(ws);

        await new Promise<void>((resolve, reject) => {
            const timeout = window.setTimeout(
                () => reject(new Error("Voice WebSocket connection timed out.")),
                15000
            );
            ws.onopen = () => { window.clearTimeout(timeout); resolve(); };
            ws.onerror = () => { window.clearTimeout(timeout); reject(new Error("Voice WebSocket connection failed.")); };
        });

        ws.onmessage = async event => {
            try {
                const message = JSON.parse(event.data);

                if (message.type === "status") {
                    if (message.status === "ai_connected" || message.status === "ai_reconnected") {
                        setCallState("connected");
                        setCallError("");
                    }
                    return;
                }

                if (message.type === "transcript") {
                    appendTranscript(
                        message.role === "customer" ? "customer" : "ai",
                        message.text
                    );
                    return;
                }

                if (message.type === "audio") {
                    await playPcm(message.data, message.sample_rate || 24000);
                    return;
                }

                if (message.type === "interruption") {
                    playbackQueueRef.current = [];
                    return;
                }

                if (message.type === "handoff_required" || message.type === "handoff") {
                    const language = message.language || "en";
                    // Close brain socket cleanly.
                    try { ws.send(JSON.stringify({ type: "stop" })); } catch {}
                    try { ws.close(); } catch {}
                    socketRef.current = null;
                    try { processorRef.current?.disconnect(); } catch {}
                    processorRef.current = null;
                    try { sourceRef.current?.disconnect(); } catch {}
                    sourceRef.current = null;

                    // Layer 2 first.
                    await speakHoldLine(language);
                    const result = await escalateToGemini(language);

                    if (result === "fallback") {
                        // Layer 3.
                        await handoffToHuman();
                    }
                    return;
                }

                if (message.type === "error") {
                    setCallError(message.message || "The AI voice service is unavailable.");
                    if (!message.recoverable) {
                        callActiveRef.current = false;
                        setCallState("error");
                        teardown();
                    }
                }
            } catch {}
        };

        ws.onclose = event => {
            if (!callActiveRef.current) return;
            if (event.code !== 1000) {
                setCallError("The AI voice connection was interrupted.");
                setCallState("error");
                callActiveRef.current = false;
                teardown();
            }
        };
    }, [appendTranscript, escalateToGemini, handoffToHuman, playPcm, prepareMic, speakHoldLine, teardown]);

    const startCall = async () => {
        setCallError("");
        setTranscript([]);
        setLayer("brain");

        const cleanPhone = phone.replace(/\D/g, "");
        if (name.trim().length < 1 || cleanPhone.length < 5) {
            setCallError("Please enter your name and mobile number first.");
            return;
        }

        setCallState("starting");
        callActiveRef.current = true;

        try {
            if (!navigator.mediaDevices?.getUserMedia) {
                throw new Error("Microphone calling is not supported in this browser.");
            }
            try {
                if ((navigator as any).wakeLock?.request) {
                    wakeLockRef.current = await (navigator as any).wakeLock.request("screen");
                }
            } catch {}

            const response = await fetch(
                API() + "/api/v1/public/business/" +
                encodeURIComponent(slug) + "/call",
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: name.trim(), phone: phone.trim() }),
                }
            );
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.detail || "Unable to start the call.");

            callIdRef.current = payload.call_id;
            setCallState("connecting");
            await openVoiceWebSocket(payload.call_id);
        } catch (error: any) {
            callActiveRef.current = false;
            teardown();
            setCallError(error?.message || "Unable to start the voice call.");
            setCallState("error");
        }
    };

    useEffect(() => () => {
        callActiveRef.current = false;
        teardown();
    }, [teardown]);

    return (
        <div className="ss-call-backdrop" role="dialog" aria-modal="true">
            <div className="ss-call-modal">
                <button className="ss-call-close" type="button" onClick={onClose} aria-label="Close">×</button>
                <h2>Talk to {businessName}</h2>
                <p className="ss-call-sub">Please enter your name and mobile number.</p>

                {(callState === "idle" || callState === "starting" || callState === "error") && (
                    <div className="ss-call-form">
                        <label>
                            Name
                            <input value={name} onChange={e => setName(e.target.value)} placeholder="Your name" autoComplete="name" />
                        </label>
                        <label>
                            Mobile number
                            <input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+91 98765 43210" autoComplete="tel" inputMode="tel" />
                        </label>
                        <button type="button" className="ss-call-start" onClick={startCall} disabled={callState === "starting"}>
                            {callState === "starting" ? "Connecting…" : "☎ Start call"}
                        </button>
                        {callError && <p className="ss-call-error">{callError}</p>}
                    </div>
                )}

                {(callState === "connecting" || callState === "connected" || callState === "ended") && (
                    <div className="ss-call-live">
                        <div className={"ss-call-pulse " + (callState === "connected" ? "active" : "")}>
                            <span>☎</span>
                        </div>
                        <strong>
                            {callState === "connected"
                                ? `AI is listening… (${layer})`
                                : callState === "connecting"
                                    ? "Connecting…"
                                    : "Call ended"}
                        </strong>
                        <div className="ss-transcript">
                            {transcript.length
                                ? transcript.map((item, index) => (
                                    <p key={index}><b>{item.role === "ai" ? "AI" : "You"}:</b> {item.text}</p>
                                ))
                                : <span>Your transcript will appear here.</span>}
                        </div>
                        {callState !== "ended" && (
                            <div className="ss-live-actions">
                                <button
                                    type="button"
                                    onClick={() => setMuted(v => { const n = !v; mutedRef.current = n; return n; })}
                                >
                                    {muted ? "Unmute" : "Mute"}
                                </button>
                                <button type="button" className="ss-end-call" onClick={endCall}>End call</button>
                            </div>
                        )}
                        {callError && <p className="ss-call-error">{callError}</p>}
                    </div>
                )}
            </div>
        </div>
    );
}