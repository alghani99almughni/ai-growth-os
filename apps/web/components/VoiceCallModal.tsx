"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { connectCustomerToStaff } from "../app/ss-nutritions/webrtc";

const API = () => String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type Props = {
    slug: string;
    businessName: string;
    agentGender?: "female" | "male";
    onClose: () => void;
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

    const requestWakeLock = useCallback(async () => {
        try {
            if (!navigator?.wakeLock?.request) return;
            if (!callActiveRef.current || document.visibilityState !== "visible") return;
            wakeLockRef.current = await navigator.wakeLock.request("screen");
        } catch {}
    }, []);

    const pickVoice = useCallback((language: string) => {
        if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
        const map: any = { en: "en-IN", hi: "hi-IN", te: "te-IN", ta: "ta-IN", kn: "kn-IN", ml: "ml-IN", mr: "mr-IN", bn: "bn-IN", gu: "gu-IN", pa: "pa-IN", ur: "ur-IN" };
        const lang = map[language] || "en-IN";
        const voices = window.speechSynthesis.getVoices();
        const pool = voices.filter(v => v.lang.toLowerCase().startsWith(lang.slice(0, 2).toLowerCase()));
        const female = ["female", "woman", "zira", "hazel", "swara", "aditi", "samantha", "ava"].some(m => pool.find(v => v.name.toLowerCase().includes(m)));
        const femaleVoice = pool.find(v => ["female", "woman", "zira", "hazel", "swara", "aditi", "samantha", "ava"].some(m => v.name.toLowerCase().includes(m)));
        const maleVoice = pool.find(v => ["male", "man", "david", "mark", "ryan", "ravi"].some(m => v.name.toLowerCase().includes(m)));
        return agentGender === "male" ? (maleVoice || pool[0]) : (femaleVoice || pool[0]);
    }, [agentGender]);

    const endCall = useCallback(() => {
        callActiveRef.current = false;
        conversationIdRef.current = null;
        try { recognitionRef.current?.stop(); } catch {}
        recognitionRef.current = null;
        try { window.speechSynthesis?.cancel(); } catch {}
        try { humanConnectionRef.current?.close(); } catch {}
        humanConnectionRef.current = null;
        try { wakeLockRef.current?.release?.(); } catch {}
        wakeLockRef.current = null;
        setCallState("ended");
    }, []);

    const handoffToHuman = useCallback(async (payload: any) => {
        try {
            setCallState("connecting");
            setCallError("Connecting you to our team…");
            try { recognitionRef.current?.stop(); } catch {}
            recognitionRef.current = null;
            speechActiveRef.current = false;

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
    }, [slug]);

    const startBrowserVoice = useCallback((payload: any) => {
        const Recognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        if (!Recognition) throw new Error("Voice calling is not supported in this browser.");
        const recognition = new Recognition();
        recognitionRef.current = recognition;
        callActiveRef.current = true;
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        const speechLangs: any = { en: "en-IN", hi: "hi-IN", te: "te-IN", ta: "ta-IN", kn: "kn-IN", ml: "ml-IN", mr: "mr-IN", bn: "bn-IN", gu: "gu-IN", pa: "pa-IN", ur: "ur-IN" };
        const browserLang = (navigator.language || "en-IN").toLowerCase();
        recognition.lang = speechLangs[browserLang.slice(0, 2)] || "en-IN";
        setCallState("connected");
        setCallError("");

        const speakTurn = async (text: string, language: string) => {
            speechActiveRef.current = true;
            try { recognition.stop(); } catch {}
            if (!("speechSynthesis" in window)) {
                speechActiveRef.current = false;
                if (callActiveRef.current) try { recognition.start(); } catch {}
                return;
            }
            window.speechSynthesis.cancel();
            await new Promise<void>(resolve => {
                const utter = new SpeechSynthesisUtterance(text);
                utter.lang = speechLangs[language] || "en-IN";
                const v = pickVoice(language);
                if (v) utter.voice = v;
                utter.rate = 0.98;
                utter.onend = () => resolve();
                utter.onerror = () => resolve();
                window.speechSynthesis.speak(utter);
            });
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
                    if (answer.language && speechLangs[answer.language]) recognition.lang = speechLangs[answer.language];
                    if (answer.handoff_required) {
                        await handoffToHuman(payload);
                    } else {
                        await speakTurn(answer.reply, answer.language || "en");
                    }
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
    }, [slug, name, businessName, pickVoice, handoffToHuman]);

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