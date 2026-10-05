"use client";

/**
 * VoiceCallModal: four-layer call orchestrator.
 *
 *  Layer 1  Assistant (free)   Browser speech -> POST /voice/turn (knowledge library + booking) -> browser speech.
 *                              Greets instantly. Never depends on Gemini.
 *  Layer 2  Specialist AI      WS /ws/escalate/{call_id} (Gemini Live, uses tokens). Only when Layer 1 asks for it.
 *  Layer 3  Human team         POST /call/{id}/handoff + WebRTC (WS /ws/calls/{id}).
 *  Layer 4  Callback ticket    POST /call/{id}/callback -> shows up in the dashboard's service requests.
 *
 * Every layer falls through to the next one on error or timeout, so the customer never hits a dead end.
 * Props follow the architecture doc: slug, businessName, existingCustomerId, onCustomerIdentified, onClose.
 *
 * v2 changes:
 *  - speech fragments are merged (1.3 s of silence) before they reach the brain ("may I know" + "the timings")
 *  - "connect me to a manager / human" goes straight to Layer 3, even in the middle of a booking
 *  - identical consecutive brain replies are treated as a loop and escalate
 *  - Layer 2 must actually speak within 15 s, otherwise we fall through to Layer 3
 *  - NEXT_PUBLIC_SPECIALIST_AI=off skips Layer 2 (brain -> human -> callback)
 *  - the specialist can ask for a human itself ("handoff_required" frame from /ws/escalate)
 */

import { useEffect, useRef, useState } from "react";

type Props = {
  slug: string;
  businessName: string;
  existingCustomerId?: string | null;
  agentGender?: "male" | "female";
  onCustomerIdentified?: (customerId: string) => void;
  onClose: () => void;
};

type Role = "customer" | "ai" | "system";
type Line = { id: number; role: Role; text: string };
type Phase =
  | "form"
  | "starting"
  | "brain"
  | "specialist"
  | "human_wait"
  | "human"
  | "callback"
  | "ended"
  | "error";
type AgentState = "listening" | "thinking" | "speaking";

const api = () => String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
const wsBase = () => api().replace(/^http:/, "ws:").replace(/^https:/, "wss:");
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

const SPECIALIST_ON = process.env.NEXT_PUBLIC_SPECIALIST_AI !== "off";
const SR_DEBOUNCE_MS = 1300;      // merge speech fragments spoken within this gap
const SPECIALIST_FIRST_SPEECH_MS = 15000;

// A customer asking for a person must never be answered by the booking flow.
const HUMAN_REQUEST = new RegExp(
  [
    String.raw`\b(manager|supervisor|superior|boss|owner|human|real person|live agent|executive|representative|customer (care|support)|someone else|somebody else)\b`,
    String.raw`\b(talk|speak|connect|transfer|put me|get me|give me)\b.{0,30}\b(person|someone|somebody|staff|team|agent|operator)\b`,
    "मैनेजर|अधिकारी|इंसान|किसी से बात|మేనేజర్|மேலாளர்",
  ].join("|"),
  "i",
);

const LANG_TAG: Record<string, string> = {
  en: "en-IN", hi: "hi-IN", te: "te-IN", ta: "ta-IN", kn: "kn-IN", ml: "ml-IN",
  mr: "mr-IN", bn: "bn-IN", gu: "gu-IN", pa: "pa-IN", ur: "ur-IN",
};

const HOLD_LINE: Record<string, string> = {
  en: "Please hold on while we connect you to the right executive.",
  hi: "कृपया प्रतीक्षा करें, हम आपको सही अधिकारी से जोड़ रहे हैं।",
  te: "దయచేసి వేచి ఉండండి, మిమ్మల్ని సరైన అధికారితో కలుపుతున్నాము.",
  ta: "தயவுசெய்து காத்திருக்கவும், உங்களை சரியான அதிகாரியுடன் இணைக்கிறோம்.",
};

const FEMALE_HINTS = ["female", "woman", "heera", "kalpana", "zira", "hazel", "neerja", "veena", "priya", "aarti", "swara", "aditi", "sara", "samantha", "aria", "jenny"];
const MALE_HINTS = ["male", "man", "ravi", "david", "mark", "george", "guy", "ryan", "daniel", "alex"];

function encodePcm16(input: Float32Array, inputRate: number, targetRate = 16000): string {
  const ratio = inputRate / targetRate;
  const length = Math.max(1, Math.round(input.length / ratio));
  const pcm = new Int16Array(length);
  for (let i = 0; i < length; i++) {
    const idx = Math.min(input.length - 1, Math.floor(i * ratio));
    const s = Math.max(-1, Math.min(1, input[idx]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(pcm.buffer);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode(...bytes.subarray(i, Math.min(i + 0x8000, bytes.length)));
  }
  return btoa(bin);
}

function decodePcm16(b64: string): Int16Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
}

/* ---------- Layer 3: customer side of the human WebRTC call ---------- */
async function connectStaff(opts: {
  slug: string;
  callId: string;
  roomToken: string;
  stream: MediaStream;
  onOffer: () => void;
  onHangup: () => void;
}): Promise<{ close: () => void }> {
  const { slug, callId, roomToken, stream } = opts;
  const iceRes = await fetch(`${api()}/api/v1/public/business/${encodeURIComponent(slug)}/voice/ice`, { cache: "no-store" });
  const iceJson = await iceRes.json().catch(() => ({}));
  const pc = new RTCPeerConnection({ iceServers: iceJson.ice_servers || [{ urls: "stun:stun.l.google.com:19302" }] });
  stream.getTracks().forEach((t) => pc.addTrack(t, stream));

  const audio = new Audio();
  audio.autoplay = true;
  audio.setAttribute("playsinline", "true");
  pc.ontrack = (ev) => {
    audio.srcObject = ev.streams[0] || new MediaStream([ev.track]);
    audio.play().catch(() => {});
  };

  const ws = new WebSocket(`${wsBase()}/ws/calls/${encodeURIComponent(callId)}?room_token=${encodeURIComponent(roomToken)}`);
  const pending: RTCIceCandidateInit[] = [];
  let remoteSet = false;
  let closed = false;

  const close = () => {
    if (closed) return;
    closed = true;
    try { ws.send(JSON.stringify({ type: "hangup" })); } catch {}
    try { ws.close(); } catch {}
    try { pc.close(); } catch {}
    audio.srcObject = null;
  };

  pc.onicecandidate = (ev) => {
    if (ev.candidate && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: "ice-candidate",
        candidate: { sdpMid: ev.candidate.sdpMid, sdpMLineIndex: ev.candidate.sdpMLineIndex, candidate: ev.candidate.candidate },
      }));
    }
  };

  ws.onmessage = async (ev) => {
    try {
      const msg = JSON.parse(ev.data);
      if (msg.type === "offer") {
        await pc.setRemoteDescription({ type: "offer", sdp: msg.sdp });
        remoteSet = true;
        for (const c of pending.splice(0)) await pc.addIceCandidate(c).catch(() => {});
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "answer", sdp: answer.sdp }));
        opts.onOffer();
      } else if (msg.type === "ice-candidate") {
        const c = msg.candidate || msg;
        if (remoteSet) await pc.addIceCandidate(c).catch(() => {});
        else pending.push(c);
      } else if (msg.type === "hangup" || msg.type === "stop") {
        close();
        opts.onHangup();
      }
    } catch {}
  };
  pc.onconnectionstatechange = () => {
    if (pc.connectionState === "failed" || pc.connectionState === "closed") {
      if (!closed) { close(); opts.onHangup(); }
    }
  };

  await new Promise<void>((resolve, reject) => {
    const t = window.setTimeout(() => reject(new Error("Human call signaling timed out.")), 15000);
    ws.onopen = () => { window.clearTimeout(t); resolve(); };
    ws.onerror = () => { window.clearTimeout(t); reject(new Error("Human call signaling failed.")); };
  });
  return { close };
}

/* ------------------------------ Component ------------------------------ */
export default function VoiceCallModal({ slug, businessName, existingCustomerId, agentGender = "female", onCustomerIdentified, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>("form");
  const [agentState, setAgentState] = useState<AgentState>("listening");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [lines, setLines] = useState<Line[]>([]);
  const [error, setError] = useState("");
  const [muted, setMuted] = useState(false);
  const [typed, setTyped] = useState("");
  const [micOk, setMicOk] = useState(true);
  const [callbackFailed, setCallbackFailed] = useState(false);

  const phaseRef = useRef<Phase>("form");
  const activeRef = useRef(false);
  const mutedRef = useRef(false);
  const busyRef = useRef(false);
  const speakingRef = useRef(false);
  const failsRef = useRef(0);
  const idleStrikesRef = useRef(0);
  const idleTimerRef = useRef<number | null>(null);
  const nameRef = useRef("");
  const phoneRef = useRef("");
  const callRef = useRef<{ call_id: string; customer_id?: string } | null>(null);
  const convRef = useRef<string | null>(null);
  const langRef = useRef("en");
  const recRef = useRef<any>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const procRef = useRef<ScriptProcessorNode | null>(null);
  const srcRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const playingRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const nextPlayRef = useRef(0);
  const escWsRef = useRef<WebSocket | null>(null);
  const humanRef = useRef<{ close: () => void } | null>(null);
  const humanPollRef = useRef<number | null>(null);
  const wakeRef = useRef<any>(null);
  const voiceCache = useRef<Record<string, SpeechSynthesisVoice | null>>({});
  const lineId = useRef(0);
  const lastLineRef = useRef<{ role: Role; at: number }>({ role: "system", at: 0 });
  const autoStartedRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const linesRef = useRef<Line[]>([]);
  const pendingRef = useRef("");
  const debounceRef = useRef<number | null>(null);
  const lastReplyRef = useRef("");
  const repeatRef = useRef(0);

  const go = (p: Phase) => { phaseRef.current = p; setPhase(p); };

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [lines]);

  /* ---------- transcript ---------- */
  const pushLine = (role: Role, raw: string, merge = false) => {
    const clean = raw.trim();
    if (!clean) return;
    const now = Date.now();
    const canMerge = merge && lastLineRef.current.role === role && now - lastLineRef.current.at < 2500;
    lastLineRef.current = { role, at: now };
    setLines((prev) => {
      let next: Line[];
      if (canMerge && prev.length && prev[prev.length - 1].role === role) {
        next = prev.slice();
        const last = next[next.length - 1];
        next[next.length - 1] = { ...last, text: (last.text + raw).replace(/\s+/g, " ").trim() };
      } else {
        next = [...prev, { id: ++lineId.current, role, text: clean }];
      }
      linesRef.current = next;
      return next;
    });
  };

  /* ---------- speech fragments -> one utterance ---------- */
  const clearPending = () => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = null;
    pendingRef.current = "";
  };
  const queueUtterance = (text: string) => {
    const t = text.trim();
    if (!t) return;
    pendingRef.current = (pendingRef.current + " " + t).trim();
    if (debounceRef.current) window.clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      const said = pendingRef.current;
      pendingRef.current = "";
      debounceRef.current = null;
      void handleUtterance(said);
    }, SR_DEBOUNCE_MS);
  };

  /* ---------- speech out (browser) ---------- */
  const pickVoice = (lang: string): SpeechSynthesisVoice | null => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return null;
    const tag = LANG_TAG[lang] || "en-IN";
    if (voiceCache.current[tag]) return voiceCache.current[tag];
    const all = window.speechSynthesis.getVoices();
    if (!all.length) return null;
    const exact = all.filter((v) => v.lang.toLowerCase() === tag.toLowerCase());
    const pool = exact.length ? exact : all.filter((v) => v.lang.toLowerCase().startsWith(tag.slice(0, 2).toLowerCase()));
    const hints = agentGender === "male" ? MALE_HINTS : FEMALE_HINTS;
    const other = agentGender === "male" ? FEMALE_HINTS : MALE_HINTS;
    const v =
      pool.find((x) => hints.some((h) => x.name.toLowerCase().includes(h))) ||
      pool.find((x) => !other.some((h) => x.name.toLowerCase().includes(h))) ||
      pool[0] || null;
    voiceCache.current[tag] = v;
    return v;
  };

  const speak = (text: string, lang = "en"): Promise<void> =>
    new Promise((resolve) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window) || !text) return resolve();
      try { window.speechSynthesis.cancel(); } catch {}
      const u = new SpeechSynthesisUtterance(text);
      u.lang = LANG_TAG[lang] || "en-IN";
      const v = pickVoice(lang);
      if (v) u.voice = v;
      u.rate = 0.98;
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        window.clearTimeout(guard);
        speakingRef.current = false;
        setAgentState("listening");
        resolve();
      };
      const guard = window.setTimeout(finish, Math.max(4000, text.length * 110));
      u.onend = finish;
      u.onerror = finish;
      speakingRef.current = true;
      setAgentState("speaking");
      window.speechSynthesis.speak(u);
    });

  /* ---------- speech in (browser) ---------- */
  const stopListening = () => { try { recRef.current?.stop(); } catch {} };

  const startListening = () => {
    if (!activeRef.current || phaseRef.current !== "brain" || speakingRef.current || busyRef.current || mutedRef.current) return;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setMicOk(false); return; }
    if (!recRef.current) {
      const rec = new SR();
      rec.continuous = true;
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = (ev: any) => {
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const r = ev.results[i];
          if (r.isFinal) queueUtterance(String(r[0]?.transcript || ""));
        }
      };
      rec.onend = () => { window.setTimeout(startListening, 250); };
      rec.onerror = (ev: any) => {
        if (ev?.error === "not-allowed" || ev?.error === "service-not-allowed") {
          setMicOk(false);
          setError("Microphone is blocked. You can type your message below instead.");
        }
      };
      recRef.current = rec;
    }
    try {
      recRef.current.lang = LANG_TAG[langRef.current] || (navigator.language || "en-IN");
      recRef.current.start();
    } catch {}
  };

  /* ---------- idle watchdog ---------- */
  const clearIdle = () => {
    if (idleTimerRef.current) window.clearTimeout(idleTimerRef.current);
    idleTimerRef.current = null;
  };
  const armIdle = () => {
    clearIdle();
    idleTimerRef.current = window.setTimeout(async () => {
      if (!activeRef.current || phaseRef.current !== "brain" || busyRef.current || speakingRef.current) { armIdle(); return; }
      idleStrikesRef.current += 1;
      if (idleStrikesRef.current >= 3) {
        const bye = `I can't hear anything, so I'll end the call now. Thank you for calling ${businessName}.`;
        pushLine("ai", bye);
        await speak(bye);
        endCall("ended");
        return;
      }
      const nudge = "Are you still there? Please tell me how I can help.";
      pushLine("ai", nudge);
      stopListening();
      await speak(nudge);
      startListening();
      armIdle();
    }, 25000);
  };

  /* ---------- Layer 1: assistant (brain) ---------- */
  const handleUtterance = async (text: string) => {
    const said = text.trim();
    if (!said || !activeRef.current || phaseRef.current !== "brain" || busyRef.current) return;
    busyRef.current = true;
    idleStrikesRef.current = 0;
    clearIdle();
    clearPending();
    stopListening();
    pushLine("customer", said);

    // Asking for a person always wins over whatever the booking flow is waiting for.
    if (HUMAN_REQUEST.test(said)) {
      busyRef.current = false;
      await humanHandoff();
      return;
    }

    setAgentState("thinking");
    try {
      const res = await fetch(`${api()}/api/v1/public/business/${encodeURIComponent(slug)}/voice/turn`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript: said,
          call_id: callRef.current?.call_id,
          conversation_id: convRef.current,
          channel: "voice",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Voice answer failed.");
      failsRef.current = 0;
      convRef.current = data.conversation_id || convRef.current;
      if (data.language) langRef.current = String(data.language);
      const reply = String(data.reply || "").trim();

      // The brain's "we'll call you back" text is not shown: the ladder decides what happens next.
      if (data.handoff_required) {
        busyRef.current = false;
        await escalate();
        return;
      }

      // Same answer twice in a row means the brain is stuck in a loop.
      const norm = reply.toLowerCase().replace(/[^a-z0-9 ]/g, "").trim();
      repeatRef.current = norm && norm === lastReplyRef.current ? repeatRef.current + 1 : 0;
      lastReplyRef.current = norm;
      if (repeatRef.current >= 1) {
        repeatRef.current = 0;
        busyRef.current = false;
        await escalate();
        return;
      }

      if (reply) {
        pushLine("ai", reply);
        await speak(reply, langRef.current);
      }
    } catch {
      failsRef.current += 1;
      if (failsRef.current >= 2) {
        busyRef.current = false;
        await escalate();
        return;
      }
      const retry = "Sorry, I had trouble with that. Could you please say it again?";
      pushLine("ai", retry);
      await speak(retry);
    }
    busyRef.current = false;
    if (phaseRef.current === "brain") {
      setAgentState("listening");
      armIdle();
      startListening();
    }
  };

  const runBrain = async () => {
    go("brain");
    const greeting = `Hello ${nameRef.current}, welcome to ${businessName}. How can I help you today?`;
    pushLine("ai", greeting);
    busyRef.current = true;
    await speak(greeting, "en");
    busyRef.current = false;
    if (!activeRef.current) return;
    armIdle();
    startListening();
  };

  /* ---------- media helpers (Layers 2 and 3) ---------- */
  const getMic = async (): Promise<MediaStream> => {
    if (micStreamRef.current) return micStreamRef.current;
    const s = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    micStreamRef.current = s;
    return s;
  };

  const clearPlayback = () => {
    playingRef.current.forEach((s) => { try { s.stop(); } catch {} });
    playingRef.current.clear();
    nextPlayRef.current = audioCtxRef.current?.currentTime || 0;
  };

  const playPcm = (b64: string, rate: number) => {
    const ctx = audioCtxRef.current;
    if (!ctx) return;
    const pcm = decodePcm16(b64);
    if (!pcm.length) return;
    const buf = ctx.createBuffer(1, pcm.length, rate);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.onended = () => playingRef.current.delete(src);
    playingRef.current.add(src);
    nextPlayRef.current = Math.max(nextPlayRef.current, ctx.currentTime);
    src.start(nextPlayRef.current);
    nextPlayRef.current += buf.duration;
  };

  const startMicStream = async (ws: WebSocket) => {
    const stream = await getMic();
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    const ctx: AudioContext = audioCtxRef.current || new Ctx();
    audioCtxRef.current = ctx;
    await ctx.resume();
    const source = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(4096, 1, 1);
    proc.onaudioprocess = (ev) => {
      if (mutedRef.current || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({ type: "audio", data: encodePcm16(ev.inputBuffer.getChannelData(0), ctx.sampleRate, 16000) }));
    };
    source.connect(proc);
    proc.connect(ctx.destination);
    srcRef.current = source;
    procRef.current = proc;
  };

  const stopMicStream = () => {
    try { procRef.current?.disconnect(); } catch {}
    try { srcRef.current?.disconnect(); } catch {}
    procRef.current = null;
    srcRef.current = null;
  };

  const closeSpecialist = () => {
    const ws = escWsRef.current;
    escWsRef.current = null;
    if (ws) {
      try { ws.send(JSON.stringify({ type: "stop" })); } catch {}
      try { ws.close(); } catch {}
    }
    stopMicStream();
    clearPlayback();
  };

  const closeHuman = () => {
    if (humanPollRef.current) window.clearInterval(humanPollRef.current);
    humanPollRef.current = null;
    humanRef.current?.close();
    humanRef.current = null;
  };

  /* ---------- Layer 2: specialist AI (Gemini Live via server bridge) ---------- */
  const openSpecialist = () =>
    new Promise<void>((resolve, reject) => {
      const callId = callRef.current?.call_id;
      if (!callId) { reject(new Error("No call")); return; }
      const ws = new WebSocket(`${wsBase()}/ws/escalate/${encodeURIComponent(callId)}`);
      escWsRef.current = ws;
      let spoke = false;     // the specialist has actually produced speech or text
      let settled = false;   // the promise below has been resolved or rejected
      let finished = false;

      const settleOk = () => { if (!settled) { settled = true; resolve(); } };
      const fail = (why: string) => {
        if (finished) return;
        finished = true;
        window.clearTimeout(firstSpeechTimer);
        closeSpecialist();
        if (!settled) { settled = true; reject(new Error(why)); }
        else if (activeRef.current) void humanHandoff();
      };
      const firstSpeechTimer = window.setTimeout(() => {
        if (!spoke && activeRef.current) fail("Specialist did not answer in time.");
      }, SPECIALIST_FIRST_SPEECH_MS);
      const markSpoke = () => {
        if (spoke) return;
        spoke = true;
        window.clearTimeout(firstSpeechTimer);
        settleOk();
      };

      ws.onopen = async () => {
        try { await startMicStream(ws); } catch { /* mic denied: the specialist can still read the context */ }
        const recent = linesRef.current.slice(-8)
          .map((l) => `${l.role === "ai" ? "Assistant" : "Customer"}: ${l.text}`).join("\n");
        const latestCustomerRequest = [...linesRef.current].reverse().find((l) => l.role === "customer")?.text || "";
        ws.send(JSON.stringify({
          type: "text",
          text: `You are joining the CURRENT call only. Customer name: ${nameRef.current}. Phone: ${phoneRef.current}.
Never say you are "taking over from the previous assistant" and never invent an unresolved booking.
Treat the customer's latest request as authoritative. If it is unrelated to the previous booking discussion, answer the new request instead of continuing the old booking.
Do not confirm or create a booking unless the customer explicitly confirms the exact date, time and service.
If the latest request is unclear, ask one short clarification question rather than guessing or handing off.
Latest customer request: ${latestCustomerRequest}
Conversation in this call:
${recent}`,
        }));
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "status") {
            if (msg.status === "ended") {
              // "ended" before the specialist ever spoke is a failure, not a finished call.
              if (!spoke) { fail("Specialist ended before answering."); return; }
              finished = true;
              window.clearTimeout(firstSpeechTimer);
              endCall("ended");
            }
            return;
          }
          if (msg.type === "error") { fail(String(msg.message || "Specialist error.")); return; }
          if (msg.type === "handoff_required") {
            // The specialist asked for a human (request_human_handoff tool). Let its last sentence finish playing first.
            if (finished) return;
            finished = true;
            window.clearTimeout(firstSpeechTimer);
            const queued = (nextPlayRef.current - (audioCtxRef.current?.currentTime || 0)) * 1000;
            window.setTimeout(() => {
              closeSpecialist();
              if (!settled) { settled = true; reject(new Error("Specialist asked for a human.")); }
              else if (activeRef.current) void humanHandoff();
            }, Math.min(8000, Math.max(0, queued) + 300));
            return;
          }
          if (msg.type === "interruption") { clearPlayback(); return; }
          if (msg.type === "transcript") {
            const isAi = ["ai", "assistant", "model"].includes(String(msg.role));
            if (isAi) markSpoke();
            pushLine(isAi ? "ai" : "customer", String(msg.text || ""), true);
            return;
          }
          if (msg.type === "audio" && msg.data) {
            markSpoke();
            playPcm(String(msg.data), Number(msg.sample_rate) || 24000);
            return;
          }
          const parts = msg?.serverContent?.modelTurn?.parts || [];
          for (const p of parts) {
            if (p?.inlineData?.data) { markSpoke(); playPcm(String(p.inlineData.data), 24000); }
          }
        } catch {}
      };
      ws.onerror = () => fail("Specialist connection failed.");
      ws.onclose = () => { if (!finished && phaseRef.current === "specialist") fail("Specialist connection closed."); };
    });

  const escalate = async () => {
    if (!activeRef.current || phaseRef.current !== "brain") return;
    clearIdle();
    clearPending();
    stopListening();
    setError("");
    if (!SPECIALIST_ON) { await humanHandoff(); return; }
    go("specialist");
    const hold = HOLD_LINE[langRef.current] || HOLD_LINE.en;
    pushLine("system", hold);
    await speak(hold, langRef.current);
    if (!activeRef.current) return;
    try {
      const Ctx = window.AudioContext || (window as any).webkitAudioContext;
      audioCtxRef.current = audioCtxRef.current || new Ctx();
      await audioCtxRef.current!.resume();
      await openSpecialist();
    } catch {
      if (activeRef.current) await humanHandoff();
    }
  };

  /* ---------- Layer 3: human team ---------- */
  const humanHandoff = async () => {
    if (!activeRef.current) return;
    if (phaseRef.current === "human_wait" || phaseRef.current === "human" || phaseRef.current === "callback") return;
    closeSpecialist();
    stopListening();
    clearIdle();
    go("human_wait");
    setError("");
    pushLine("system", "Connecting you to our team…");
    void speak("Connecting you to our team. Please hold.", langRef.current);

    const callId = callRef.current?.call_id;
    if (!callId) { await requestCallback("No active call."); return; }
    const base = `${api()}/api/v1/public/business/${encodeURIComponent(slug)}/call/${encodeURIComponent(callId)}/handoff`;
    try {
      const first = await fetch(base, { method: "POST" });
      const data = await first.json().catch(() => ({}));
      if (!first.ok) throw new Error(String(data.detail || "Human handoff is unavailable."));
      if (data.status === "handoff_unavailable") { await requestCallback("No team member was available."); return; }

      let token = String(data.room_token || "");
      for (let i = 0; i < 45 && activeRef.current && !token; i++) {
        await sleep(1000);
        const r = await fetch(base, { cache: "no-store" });
        if (!r.ok) continue;
        const s = await r.json().catch(() => ({}));
        if (s.status === "handoff_unavailable" || s.status === "handoff_declined") {
          await requestCallback("No team member was available.");
          return;
        }
        token = String(s.room_token || "");
      }
      if (!activeRef.current) return;
      if (!token) { await requestCallback("The team did not answer in time."); return; }

      const stream = await getMic();
      let offered = false;
      humanRef.current = await connectStaff({
        slug,
        callId,
        roomToken: token,
        stream,
        onOffer: () => {
          offered = true;
          if (humanPollRef.current) window.clearInterval(humanPollRef.current);
          humanPollRef.current = null;
          go("human");
          pushLine("system", "Connected to our team.");
        },
        onHangup: () => { if (phaseRef.current === "human") endCall("ended"); else if (!offered && activeRef.current) void requestCallback("The team member could not take the call."); },
      });

      // Staff must accept within 45 seconds, otherwise raise a callback ticket.
      const started = Date.now();
      humanPollRef.current = window.setInterval(async () => {
        if (!activeRef.current || offered) return;
        if (Date.now() - started > 45000) { closeHuman(); await requestCallback("The team did not answer in time."); return; }
        try {
          const r = await fetch(base, { cache: "no-store" });
          if (!r.ok) return;
          const s = await r.json().catch(() => ({}));
          if (s.status === "handoff_declined" || s.status === "handoff_unavailable") {
            closeHuman();
            await requestCallback("The team member could not take the call.");
          }
        } catch {}
      }, 2000);
    } catch (e: any) {
      closeHuman();
      if (activeRef.current) await requestCallback(String(e?.message || "Human handoff failed."));
    }
  };

  /* ---------- Layer 4: callback ticket ---------- */
  const requestCallback = async (reason: string) => {
    if (!activeRef.current || phaseRef.current === "callback") return;
    closeSpecialist();
    closeHuman();
    stopListening();
    clearIdle();
    go("callback");
    setCallbackFailed(false);
    await saveCallback(reason);
  };

  const saveCallback = async (reason: string) => {
    const callId = callRef.current?.call_id;
    let saved = false;
    if (callId) {
      try {
        const r = await fetch(`${api()}/api/v1/public/business/${encodeURIComponent(slug)}/call/${encodeURIComponent(callId)}/callback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason }),
        });
        saved = r.ok;
      } catch {}
    }
    const msg = saved
      ? `Sorry, our team is busy right now. We have noted your request and someone will call you back on ${phoneRef.current}. Thank you for calling ${businessName}.`
      : "Sorry, we could not reach our team and could not save your callback request. Please try again.";
    setCallbackFailed(!saved);
    pushLine("ai", msg);
    if (saved) setError("");
    else setError("Callback request was not saved.");
    await speak(msg, "en");
    if (saved) activeRef.current = false;
  };

  /* ---------- start / end ---------- */
  const endCall = (final: Phase = "ended") => {
    activeRef.current = false;
    clearIdle();
    clearPending();
    stopListening();
    try { recRef.current = null; } catch {}
    try { window.speechSynthesis?.cancel(); } catch {}
    closeSpecialist();
    closeHuman();
    try { micStreamRef.current?.getTracks().forEach((t) => t.stop()); } catch {}
    micStreamRef.current = null;
    try { audioCtxRef.current?.close(); } catch {}
    audioCtxRef.current = null;
    try { wakeRef.current?.release?.(); } catch {}
    wakeRef.current = null;
    go(final);
  };

  const startCall = async (nm: string, ph: string, customerId?: string | null) => {
    setError("");
    // Every new call starts with a clean conversation boundary.
    convRef.current = null;
    if (nm.trim().length < 1 || ph.replace(/\D/g, "").length < 5) {
      setError("Please enter your name and mobile number first.");
      return;
    }
    nameRef.current = nm.trim();
    phoneRef.current = ph.trim();
    activeRef.current = true;
    convRef.current = null;
    failsRef.current = 0;
    idleStrikesRef.current = 0;
    setLines([]);
    setMicOk(true);
    go("starting");
    try { wakeRef.current = await (navigator as any).wakeLock?.request?.("screen"); } catch {}
    try {
      const body: Record<string, string> = { name: nm.trim(), phone: ph.trim() };
      if (customerId) body.customer_id = customerId;
      const res = await fetch(`${api()}/api/v1/public/business/${encodeURIComponent(slug)}/call`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(String(data.detail || "Unable to start the call."));
      callRef.current = { call_id: data.call_id, customer_id: data.customer_id };
      if (data.customer_id) { try { onCustomerIdentified?.(String(data.customer_id)); } catch {} }
      try {
        if (data.customer_id) localStorage.setItem(`cust:${slug}:id`, data.customer_id);
        localStorage.setItem(`cust:${slug}:name`, nm.trim());
        localStorage.setItem(`cust:${slug}:phone`, ph.trim());
        localStorage.setItem("cust:last-business", slug);
      } catch {}
      await runBrain();
    } catch (e: any) {
      activeRef.current = false;
      callRef.current = null;
      setError(String(e?.message || "Unable to start the call."));
      go("error");
    }
  };

  useEffect(() => {
    try {
      const n = localStorage.getItem(`cust:${slug}:name`) || "";
      const p = localStorage.getItem(`cust:${slug}:phone`) || "";
      if (n) setName(n);
      if (p) setPhone(p);
      if (existingCustomerId && n && p && !autoStartedRef.current) {
        autoStartedRef.current = true;
        void startCall(n, p, existingCustomerId);
      }
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, existingCustomerId]);

  useEffect(() => () => { endCall("ended"); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const toggleMute = () => {
    const next = !mutedRef.current;
    mutedRef.current = next;
    setMuted(next);
    if (next) stopListening();
    else startListening();
  };

  const sendTyped = () => {
    const t = typed.trim();
    if (!t) return;
    setTyped("");
    void handleUtterance(t);
  };

  const closeModal = () => { endCall("ended"); onClose(); };

  /* ------------------------------ render ------------------------------ */
  const showForm = phase === "form" || phase === "starting" || (phase === "error" && !callRef.current);
  const live = !showForm;
  const finished = phase === "ended" || (phase === "callback" && !callbackFailed);

  const statusText: Record<Phase, string> = {
    form: "",
    starting: "Connecting…",
    brain: agentState === "speaking" ? "Assistant is speaking…" : agentState === "thinking" ? "Assistant is thinking…" : "Assistant is listening…",
    specialist: "Specialist AI is on the line…",
    human_wait: "Connecting you to our team…",
    human: "Connected to our team",
    callback: callbackFailed ? "Callback not saved" : "Callback requested",
    ended: "Call ended",
    error: "",
  };
  const layerLabel: Partial<Record<Phase, string>> = {
    brain: "Assistant", specialist: "Specialist AI", human_wait: "Human team", human: "Human team", callback: "Callback",
  };

  return (
    <div className="vcm-backdrop" role="dialog" aria-modal="true" aria-label={`Call ${businessName}`}>
      <style>{CSS}</style>
      <div className="vcm-card">
        <button className="vcm-close" type="button" onClick={closeModal} aria-label="Close">×</button>
        <h2 className="vcm-title">Talk to {businessName}</h2>

        {showForm && (
          <div>
            <p className="vcm-sub">Please enter your name and mobile number.</p>
            <label className="vcm-label">Name
              <input className="vcm-input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" autoComplete="name" />
            </label>
            <label className="vcm-label">Mobile number
              <input className="vcm-input" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 98765 43210" autoComplete="tel" inputMode="tel" />
            </label>
            <button className="vcm-primary" type="button" disabled={phase === "starting"} onClick={() => void startCall(name, phone, existingCustomerId)}>
              {phase === "starting" ? "Connecting…" : "☎ Start call"}
            </button>
            {error && <p className="vcm-error">{error}</p>}
          </div>
        )}

        {live && (
          <div className="vcm-live">
            <div className={`vcm-pulse ${phase === "brain" || phase === "specialist" || phase === "human" ? "on" : ""}`}><span>☎</span></div>
            <strong className="vcm-status">{statusText[phase]}</strong>
            {layerLabel[phase] && <span className="vcm-chip">{layerLabel[phase]}</span>}

            <div className="vcm-transcript" ref={scrollRef}>
              {lines.length === 0 && <span className="vcm-muted">Your conversation will appear here.</span>}
              {lines.map((l) => (
                <p key={l.id} className={`vcm-line vcm-${l.role}`}>
                  {l.role !== "system" && <b>{l.role === "ai" ? "AI" : "You"}: </b>}
                  {l.text}
                </p>
              ))}
            </div>

            {phase === "brain" && (
              <div className="vcm-typed">
                <input
                  className="vcm-input"
                  value={typed}
                  onChange={(e) => setTyped(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") sendTyped(); }}
                  placeholder={micOk ? "Or type your message…" : "Microphone unavailable. Type here…"}
                />
                <button className="vcm-secondary" type="button" onClick={sendTyped}>Send</button>
              </div>
            )}

            {error && <p className="vcm-error">{error}</p>}

            <div className="vcm-actions">
              {phase === "callback" && callbackFailed && (
                <button className="vcm-secondary" type="button" onClick={() => { setCallbackFailed(false); void saveCallback("Retry from customer."); }}>
                  Try callback again
                </button>
              )}
              {!finished && phase !== "callback" && (
                <button className="vcm-secondary" type="button" onClick={toggleMute}>{muted ? "Unmute" : "Mute"}</button>
              )}
              {finished || phase === "callback" ? (
                <button className="vcm-primary" type="button" onClick={closeModal}>Close</button>
              ) : (
                <button className="vcm-end" type="button" onClick={() => endCall("ended")}>End call</button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const CSS = `
.vcm-backdrop{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;padding:16px;background:rgba(6,30,22,.55);backdrop-filter:blur(6px)}
.vcm-card{position:relative;width:100%;max-width:460px;max-height:92vh;overflow:auto;border-radius:24px;background:#faf6ee;color:#0b3326;padding:28px 24px;box-shadow:0 24px 60px rgba(0,0,0,.28);font-family:inherit}
.vcm-close{position:absolute;top:14px;right:16px;border:0;background:none;font-size:30px;line-height:1;cursor:pointer;color:#0b3326}
.vcm-title{margin:0 36px 6px 0;font-size:30px;line-height:1.1;font-weight:800;letter-spacing:-.02em}
.vcm-sub{margin:0 0 16px;color:#5a7268}
.vcm-label{display:block;margin:12px 0 0;font-weight:700;font-size:14px}
.vcm-input{display:block;width:100%;box-sizing:border-box;margin-top:6px;padding:13px 14px;border-radius:14px;border:1px solid #d6dfd9;background:#fff;font-size:16px;color:#0b3326}
.vcm-primary,.vcm-secondary,.vcm-end{border:0;border-radius:14px;padding:13px 18px;font-size:16px;font-weight:700;cursor:pointer}
.vcm-primary{width:100%;margin-top:18px;background:#1a5c43;color:#fff}
.vcm-primary:disabled{opacity:.6;cursor:default}
.vcm-secondary{background:#fff;color:#0b3326;border:1px solid #d6dfd9}
.vcm-end{background:#b6341f;color:#fff;flex:1}
.vcm-error{margin:10px 0 0;color:#b6341f;font-size:14px}
.vcm-live{display:flex;flex-direction:column;align-items:center;gap:10px;margin-top:6px}
.vcm-pulse{width:84px;height:84px;border-radius:50%;background:#dfeae3;display:flex;align-items:center;justify-content:center;font-size:30px}
.vcm-pulse.on{animation:vcmPulse 1.6s ease-in-out infinite}
@keyframes vcmPulse{0%,100%{box-shadow:0 0 0 0 rgba(26,92,67,.35)}50%{box-shadow:0 0 0 14px rgba(26,92,67,0)}}
.vcm-status{font-size:17px}
.vcm-chip{font-size:12px;padding:3px 10px;border-radius:999px;background:#e3efe8;color:#1a5c43;font-weight:700}
.vcm-transcript{width:100%;box-sizing:border-box;min-height:96px;max-height:230px;overflow:auto;padding:12px 14px;border-radius:16px;background:#fff;border:1px solid #e6ece8;text-align:left}
.vcm-line{margin:0 0 8px;font-size:15px;line-height:1.4}
.vcm-system{color:#5a7268;font-style:italic}
.vcm-muted{color:#8a9c93}
.vcm-typed{display:flex;gap:8px;width:100%}
.vcm-typed .vcm-input{margin-top:0}
.vcm-actions{display:flex;gap:10px;width:100%;margin-top:4px}
.vcm-actions .vcm-primary{margin-top:0}
`;
