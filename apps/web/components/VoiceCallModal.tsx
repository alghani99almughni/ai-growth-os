"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { connectCustomerToStaff } from "../app/ss-nutritions/webrtc";

const API = () => String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const WS_API = () => API().replace(/^http:/, "ws:").replace(/^https:/, "wss:");

type Props = {
    slug: string;
    businessName: string;
    agentGender?: "female" | "male";
    onClose: () => void;
};

const HOLD_LINE: Record<string, string> = {
    en: "Please hold on while we connect you to the right executive.",
    hi: "कृपया प्रतीक्षा करें, हम आपको हमारी टीम से जोड़ रहे हैं।",
    te: "దయచేసి వెచి ఉండండి, మేము మిమ్మల్ని మా టీమ్‌కు కనెక్ట్ చేస్తున్నాము.",
    ta: "தயவுசெய்து காத்திருங்கள், நாங்கள் உங்களை எங்கள் குழுவுடன் இணைக்கிறோம்.",
    kn: "ದಯವಿಟ್ಟು ನಿರೀಕ್ಷಿಸಿ, ನಾವು ನಿಮ್ಮನ್ನು ನಮ್ಮ ತಂಡಕ್ಕೆ ಸಂಪರ್ಕಿಸುತ್ತಿದ್ದೇವೆ.",
    ml: "ദയവായി കാത്തിരിക്കുക, ഞങ്ങൾ നിങ്ങളെ ഞങ്ങളുടെ ടീമുമായി ബന്ധിപ്പിക്കുന്നു.",
    mr: "कृपया थांबा, आम्ही तुम्हाला आमच्या टीमशी जोडत आहोत.",
    bn: "অনুগ্রহ করে অপেক্ষা করুন, আমরা আপনাকে আমাদের দলের সাথে সংযুক্ত করছি।",
    gu: "કૃપા કરીને રાહ જુઓ, અમે તમને અમારી ટીમ સાથે જોડી રહ્યા છીએ.",
    pa: "ਕਿਰਪਾ ਕਰਕੇ ਉਡੀਕ ਕਰੋ, ਅਸੀਂ ਤੁਹਾਨੂੰ ਸਾਡੀ ਟੀਮ ਨਾਲ ਜੋੜ ਰਹੇ ਹਾਂ।",
    ur: "براہ کرم انتظار کریں، ہم آپ کو ہماری ٹیم سے جوڑ رہے ہیں۔",
};

const SPEECH_LANGS: Record<string, string> = {
    en: "en-IN", hi: "hi-IN", te: "te-IN", ta: "ta-IN", kn: "kn-IN",
    ml: "ml-IN", mr: "mr-IN", bn: "bn-IN", gu: "gu-IN", pa: "pa-IN", ur: "ur-IN",
};

export default function VoiceCallModal({ slug, businessName, agentGender = "female", onClose }: Props) {
    const [callState, setCallState] = useState<"idle" | "starting" | "connecting" | "connected" | "ended" | "error">("idle");
    const [name, setName] = useState("");
    const [phone, setPhone] = useState("");
    const [callError, setCallError] = useState("");
    const [transcript, setTranscript] = useState<{ role: string; text: string }[]>([]);
    const [muted, setMuted] = useState(false);
    const mutedRef = useRef(false);
    const recognitionRef = useRef<any>(null);
    const callActiveRef = useRef(false);
    const speechActiveRef = useRef(false);
    const conversationIdRef = useRef<string | null>(null);
    const wakeLockRef = useRef<any>(null);
    const humanConnectionRef = useRef<any>(null);
    const geminiSocketRef = useRef<WebSocket | null>(null);
    const geminiAudioCtxRef = useRef<AudioContext | null>(null);
    const geminiInputRef = useRef<MediaStreamAudioSourceNode | null>(null);
    const geminiProcessorRef = useRef<ScriptProcessorNode | null>(null);
    const geminiMicRef = useRef<MediaStream | null>(null);
    const geminiPlaybackQueueRef = useRef<Float32Array[]>([]);
    const geminiPlayingRef = useRef(false);

    const requestWakeLock = useCallback(async () => {
        try {
            if (!navigator?.wakeLock?.request) return;
            if (!callActiveRef.current || document.visibilityState !== "visible") return;
            wakeLockRef.current = await navigator.wakeLock.request("screen");
        } catch {}
    }, []);

    const pickVoice = useCallback((language: string) => {
        if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
        const lang = SPEECH_LANGS[language] || "en-IN";
        const voices = window.speechSynthesis.getVoices();
        const pool = voices.filter(v => v.lang.toLowerCase().startsWith(lang.slice(0, 2).toLowerCase()));
        const femaleVoice = pool.find(v => ["female", "woman", "zira", "hazel", "swara", "aditi", "samantha", "ava"].some(m => v.name.toLowerCase().includes(m)));
        const maleVoice = pool.find(v => ["male", "man", "david", "mark", "ryan", "ravi"].some(m => v.name.toLowerCase().includes(m)));
        return agentGender === "male" ? (maleVoice || pool[0]) : (femaleVoice || pool[0]);
    }, [agentGender]);

    const speakText = useCallback(async (text: string, language: string) => {
        if (!("speechSynthesis" in window)) return;
        window.speechSynthesis.cancel();
        await new Promise<void>(resolve => {
            const utter = new SpeechSynthesisUtterance(text);
            utter.lang = SPEECH_LANGS[language] || "en-IN";
            const v = pickVoice(language);
            if (v) utter.voice = v;
            utter.rate = 0.98;
            utter.onend = () => resolve();
            utter.onerror = () => resolve();
            window.speechSynthesis.speak(utter);
        });
    }, [pickVoice]);

    const teardownGemini = useCallback(() => {
        try { geminiSocketRef.current?.close(); } catch {}
        geminiSocketRef.current = null;
        try { geminiProcessorRef.current?.disconnect(); } catch {}
        geminiProcessorRef.current = null;
        try { geminiInputRef.current?.disconnect(); } catch {}
        geminiInputRef.current = null;
        try { geminiMicRef.current?.getTracks().forEach(t => t.stop()); } catch {}
        geminiMicRef.current = null;
        try { geminiAudioCtxRef.current?.close(); } catch {}
        geminiAudioCtxRef.current = null;
        geminiPlaybackQueueRef.current = [];
        geminiPlayingRef.current = false;
    }, []);

    const endCall = useCallback(() => {
        callActiveRef.current = false;
        conversationIdRef.current = null;
        try { recognitionRef.current?.stop(); } catch {}
        recognitionRef.current = null;
        try { window.speechSynthesis?.cancel(); } catch {}
        try { humanConnectionRef.current?.close(); } catch {}
        humanConnectionRef.current = null;
        teardownGemini();
        try { wakeLockRef.current?.release?.(); } catch {}
        wakeLockRef.current = null;
        setCallState("ended");
    }, [teardownGemini]);

    const playGeminiPcm = useCallback(async (base64Data: string, sampleRate: number) => {
        const ctx = geminiAudioCtxRef.current;
        if (!ctx) return;
        const raw = atob(base64Data);
        const bytes = new Uint8Array(raw.length);
        for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
        const view = new DataView(bytes.buffer);
        const sampleCount = Math.floor(bytes.byteLength / 2);
        const samples = new Float32Array(new ArrayBuffer(sampleCount * 4));
        for (let i = 0; i < sampleCount; i++) samples[i] = view.getInt16(i * 2, true) / 32768;
        geminiPlaybackQueueRef.current.push(samples);
        if (geminiPlayingRef.current) return;
        geminiPlayingRef.current = true;
        try {
            while (geminiPlaybackQueueRef.current.length && callActiveRef.current) {
                const chunk = geminiPlaybackQueueRef.current.shift()!;
                const buffer = ctx.createBuffer(1, chunk.length, sampleRate);
                buffer.copyToChannel(chunk, 0);
                const source = ctx.createBufferSource();
                source.buffer = buffer;
                source.connect(ctx.destination);
                await new Promise<void>(resolve => {
                    source.onended = () => resolve();
                    source.start();
                });
            }
        } finally {
            geminiPlayingRef.current = false;
        }
    }, []);

    const startGeminiEscalation = useCallback(async (callId: string, language: string) => {
        await speakText(HOLD_LINE[language] || HOLD_LINE.en, language);
        setCallError("Connecting you to the right executive…");

        const ws = new WebSocket(`${WS_API()}/ws/escalate/${encodeURIComponent(callId)}`);
        geminiSocketRef.current = ws;

        const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
        geminiAudioCtxRef.current = ctx;
        await ctx.resume();

        const mic = await navigator.mediaDevices.getUserMedia({
            audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true }
        });
        geminiMicRef.current = mic;
        const source = ctx.createMediaStreamSource(mic);
        geminiInputRef.current = source;

        const processor = ctx.createScriptProcessor(4096, 1, 1);
        geminiProcessorRef.current = processor;
        const ratio = ctx.sampleRate / 16000;
        processor.onaudioprocess = ev => {
            if (mutedRef.current || ws.readyState !== WebSocket.OPEN || !callActiveRef.current) return;
            const input = ev.inputBuffer.getChannelData(0);
            const outLen = Math.max(1, Math.round(input.length / ratio));
            const pcm = new Int16Array(outLen);
            for (let i = 0; i < outLen; i++) {
                const s = Math.max(-1, Math.min(1, input[Math.min(input.length - 1, Math.floor(i * ratio))]));
                pcm[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            const bytes = new Uint8Array(pcm.buffer);
            let bin = "";
            const CHUNK = 32768;
            for (let i = 0; i < bytes.length; i += CHUNK) {
                bin += String.fromCharCode(...bytes.subarray(i, Math.min(i + CHUNK, bytes.length)));
            }
            ws.send(JSON.stringify({ type: "audio", data: btoa(bin) }));
        };
        source.connect(processor);
        processor.connect(ctx.destination);

        await new Promise<void>((resolve, reject) => {
            ws.onopen = () => resolve();
            ws.onerror = () => reject(new Error("Escalation socket failed."));
        });

        ws.onmessage = async ev => {
            try {
                const msg = JSON.parse(ev.data);
                if (msg.type === "status" && msg.status === "connected") {
                    setCallState("connected");
                    setCallError("");
                    return;
                }
                if (msg.type === "transcript") {
                    setTranscript(prev => [...prev, { role: msg.role, text: msg.text }]);
                    return;
                }
                if (msg.type === "audio") {
                    await playGeminiPcm(msg.data, msg.sample_rate || 24000);
                    return;
                }
                if (msg.type === "error") {
                    setCallError(msg.message || "AI voice failed.");
                    return;
                }
            } catch {}
        };

        ws.onclose = () => {
            if (callActiveRef.current) {
                teardownGemini();
                endCall();
            }
        };
    }, [playGeminiPcm, speakText, teardownGemini, endCall]);

    const handoffToHuman = useCallback(async (payload: any) => {
        try {
            setCallState("connecting");
            setCallError("Connecting you to our team…");
            try { recognitionRef.current?.stop(); } catch {}
            recognitionRef.current = null;
            speechActiveRef.current = false;
            teardownGemini();

            const activate = await fetch(API() + "/api/v1/public/business/" + encodeURIComponent(slug) + "/call/" + encodeURIComponent(payload.call_id) + "/handoff", { method: "POST" });
            const activation = await activate.json();
            if (!activate.ok) throw new Error(activation.detail || "Human handoff is unavailable.");
            if (activation.status === "handoff_unavailable") throw new Error("No team member is available right now.");

            let roomToken = activation.room_token || "";
            for (let attempt = 0; attempt < 90; attempt++) {
                if (!callActiveRef.current) return;
                if (roomToken) {
                    const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
                    humanConnectionRef.current = await connectCustomerToStaff(API(), slug, payload.call_id, roomToken, stream);
                    setCallState("connected");
                    setCallError("Connected to our team.");
                    return;
                }
                await new Promise(r => setTimeout(r, 1000));
                const statusResponse = await fetch(API() + "/api/v1/public/business/" + encodeURIComponent(slug) + "/call/" + encodeURIComponent(payload.call_id) + "/handoff", { cache: "no-store" });
                if (statusResponse.ok) {
                    const status = await statusResponse.json();
                    roomToken = status.room_token || "";
                    if (status.status === "handoff_unavailable") throw new Error("No team member is available right now.");
                }
            }
            throw new Error("The team did not answer in time.");
        } catch (e: any) {
            setCallError(e?.message || "Human handoff failed.");
            callActiveRef.current = false;
            setCallState("ended");
        }
    }, [slug, teardownGemini]);

    const startBrowserVoice = useCallback((payload: any) => {
        const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (!Recognition) throw new Error("Voice calling is not supported in this browser.");
        const recognition = new Recognition();
        recognitionRef.current = recognition;
        callActiveRef.current = true;
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        const browserLang = (navigator.language || "en-IN").toLowerCase();
        recognition.lang = SPEECH_LANGS[browserLang.slice(0, 2)] || "en-IN";
        setCallState("connected");
        setCallError("");

        const speakTurn = async (text: string, language: string) => {
            speechActiveRef.current = true;
            try { recognition.stop(); } catch {}
            await speakText(text, language);
            speechActiveRef.current = false;
            if (callActiveRef.current) try { recognition.start(); } catch {}
        };

        const greeting = `Hello ${name.trim() || "there"}, welcome to ${businessName}. How can I help you today?`;
        setTranscript([{ role: "ai", text: greeting }]);

        recognition.onresult = async (event: any) => {
            if (speechActiveRef.current || !callActiveRef.current) return;
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const result = event.results[i];
                if (!result.isFinal) continue;
                const text = String(result[0]?.transcript || "").trim();
                if (!text || !callActiveRef.current || speechActiveRef.current) continue;
                try { recognition.stop(); } catch {}
                setTranscript(prev => [...prev, { role: "customer", text }]);
                try {
                    const rr = await fetch(API() + "/api/v1/public/business/" + encodeURIComponent(slug) + "/voice/turn", {
                        method: "POST", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ transcript: text, call_id: payload.call_id, conversation_id: conversationIdRef.current, channel: "voice" })
                    });
                    const answer = await rr.json();
                    if (!rr.ok) throw new Error(answer.detail || "Voice answer failed.");
                    conversationIdRef.current = answer.conversation_id || conversationIdRef.current;
                    setTranscript(prev => [...prev, { role: "ai", text: answer.reply }]);
                    if (answer.language && SPEECH_LANGS[answer.language]) recognition.lang = SPEECH_LANGS[answer.language];

                    if (answer.next_step === "escalate") {
                        try { recognition.stop(); } catch {}
                        recognitionRef.current = null;
                        try {
                            await startGeminiEscalation(payload.call_id, answer.language || "en");
                            return;
                        } catch {
                            await handoffToHuman(payload);
                            return;
                        }
                    }
                    if (answer.handoff_required) {
                        await handoffToHuman(payload);
                        return;
                    }
                    await speakTurn(answer.reply, answer.language || "en");
                } catch (e: any) {
                    setCallError(e?.message || "I could not answer that. Please try again.");
                    speechActiveRef.current = false;
                    if (callActiveRef.current) try { recognition.start(); } catch {}
                }
            }
        };
        recognition.onerror = (e: any) => {
            if (!callActiveRef.current) return;
            if (e?.error === "not-allowed" || e?.error === "service-not-allowed") {
                callActiveRef.current = false;
                setCallError("Microphone access is required.");
                setCallState("error");
            }
        };
        recognition.onend = () => {
            if (callActiveRef.current && !speechActiveRef.current) try { recognition.start(); } catch {}
        };
        (async () => { await speakTurn(greeting, "en"); })().catch(() => {});
    }, [slug, name, businessName, speakText, handoffToHuman, startGeminiEscalation]);

    const startCall = async () => {
        setCallError(""); setTranscript([]); conversationIdRef.current = null;
        if (name.trim().length < 1 || phone.replace(/\D/g, "").length < 5) {
            setCallError("Please enter your name and mobile number first."); return;
        }
        setCallState("starting");
        callActiveRef.current = true;
        await requestWakeLock();
        try {
            const start = await fetch(API() + "/api/v1/public/business/" + encodeURIComponent(slug) + "/call", {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: name.trim(), phone: phone.trim() })
            });
            const payload = await start.json();
            if (!start.ok) throw new Error(payload.detail || "Unable to start the call.");
            startBrowserVoice(payload);
        } catch (e: any) {
            callActiveRef.current = false;
            setCallError(e?.message || "Unable to start the call.");
            setCallState("error");
        }
    };

    useEffect(() => () => endCall(), [endCall]);

    return (
        <div className="ss-call-backdrop" role="dialog" aria-modal="true">
            <div className="ss-call-modal">
                <button className="ss-call-close" type="button" onClick={onClose} aria-label="Close">×</button>
                <h2>Talk to {businessName}</h2>
                <p className="ss-call-sub">Please enter your name and mobile number.</p>
                {(callState === "idle" || callState === "starting" || callState === "error") && (
                    <div className="ss-call-form">
                        <label>Name<input value={name} onChange={e => setName(e.target.value)} placeholder="Your name" autoComplete="name" /></label>
                        <label>Mobile number<input value={phone} onChange={e => setPhone(e.target.value)} placeholder="+91 98765 43210" autoComplete="tel" inputMode="tel" /></label>
                        <button type="button" className="ss-call-start" onClick={startCall} disabled={callState === "starting"}>
                            {callState === "starting" ? "Connecting…" : "☎ Start call"}
                        </button>
                        {callError && <p className="ss-call-error">{callError}</p>}
                    </div>
                )}
                {(callState === "connecting" || callState === "connected" || callState === "ended") && (
                    <div className="ss-call-live">
                        <div className={"ss-call-pulse " + (callState === "connected" ? "active" : "")}><span>☎</span></div>
                        <strong>{callState === "connected" ? "AI is listening…" : callState === "connecting" ? "Connecting…" : "Call ended"}</strong>
                        <div className="ss-transcript">
                            {transcript.length ? transcript.map((item, i) => (
                                <p key={i}><b>{item.role === "ai" ? "AI" : "You"}:</b> {item.text}</p>
                            )) : <span>Your transcript will appear here.</span>}
                        </div>
                        {callState !== "ended" && (
                            <div className="ss-live-actions">
                                <button type="button" onClick={() => setMuted(v => { const n = !v; mutedRef.current = n; return n; })}>{muted ? "Unmute" : "Mute"}</button>
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