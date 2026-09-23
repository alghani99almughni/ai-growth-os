"use client";
import {useCallback,useEffect,useMemo,useRef,useState} from "react";

const api=()=>String(process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000").replace(/\/+$/,"");

const fallback={
  eyebrow:"MOINABAD · RANGAREDDY · TELANGANA",
  hero_title:"Feel better.",
  hero_emphasis:"Live consciously.",
  hero_description:"Practical wellness for modern life, with an organic-focused approach to healthier everyday choices.",
  about_title:"Health consciousness starts with what you do every day.",
  about_text:"SS Nutritions is a local wellness brand based in Moinabad, focused on helping people make informed, sustainable lifestyle choices.",
  whatsapp_number:"",
  contact_heading:"Your wellness journey can start with one conversation.",
  contact_text:"Tell us what you are looking for and our team can guide you on the next step.",
  quote:"Wellness is not about changing everything overnight. It is about making better choices, consistently."
};

function encodePcm16(float32:Float32Array,inputRate:number,targetRate=16000){
  const ratio=inputRate/targetRate;
  const length=Math.max(1,Math.round(float32.length/ratio));
  const pcm=new Int16Array(length);
  for(let i=0;i<length;i++){
    const index=Math.min(float32.length-1,Math.floor(i*ratio));
    const sample=Math.max(-1,Math.min(1,float32[index]));
    pcm[i]=sample<0?sample*0x8000:sample*0x7fff;
  }
  const bytes=new Uint8Array(pcm.buffer);
  let binary="";
  const chunk=0x8000;
  for(let i=0;i<bytes.length;i+=chunk) binary+=String.fromCharCode(...bytes.subarray(i,Math.min(i+chunk,bytes.length)));
  return btoa(binary);
}

function decodeBase64Pcm16(base64:string){
  const binary=atob(base64);
  const bytes=new Uint8Array(binary.length);
  for(let i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i);
  return new Int16Array(bytes.buffer);
}

export default function SSNutritions(){
  const [data,setData]=useState<any>(null);
  const [callOpen,setCallOpen]=useState(false);
  const [callState,setCallState]=useState<"idle"|"starting"|"connecting"|"connected"|"ended"|"error">("idle");
  const [name,setName]=useState("");
  const [phone,setPhone]=useState("");
  const [callError,setCallError]=useState("");
  const [transcript,setTranscript]=useState<Array<{role:string;text:string}>>([]);
  const [muted,setMuted]=useState(false);
  const mutedRef=useRef(false);
  const socketRef=useRef<WebSocket|null>(null);
  const streamRef=useRef<MediaStream|null>(null);
  const audioContextRef=useRef<AudioContext|null>(null);
  const processorRef=useRef<ScriptProcessorNode|null>(null);
  const sourceRef=useRef<MediaStreamAudioSourceNode|null>(null);
  const nextAudioTimeRef=useRef(0);
  const recognitionRef=useRef<any>(null);
  const callActiveRef=useRef(false);
  const speechActiveRef=useRef(false);
  const conversationIdRef=useRef<string|null>(null);
  const wakeLockRef=useRef<any>(null);

  const requestWakeLock=useCallback(async()=>{
    try{
      if(typeof navigator==="undefined" || !(navigator as any).wakeLock?.request) return;
      if(!callActiveRef.current || document.visibilityState!=="visible") return;
      wakeLockRef.current=await (navigator as any).wakeLock.request("screen");
      wakeLockRef.current?.addEventListener?.("release",()=>{wakeLockRef.current=null;});
    }catch{}
  },[]);

  useEffect(()=>{
    const onVisibility=()=>{
      if(document.visibilityState==="visible" && callActiveRef.current){
        requestWakeLock();
        try{audioContextRef.current?.resume()}catch{}
      }
    };
    document.addEventListener("visibilitychange",onVisibility);
    return()=>document.removeEventListener("visibilitychange",onVisibility);
  },[requestWakeLock]);

  useEffect(()=>{
    fetch(api()+"/api/v1/public/business/resolve?name="+encodeURIComponent("SS Nutritions"))
      .then(r=>r.ok?r.json():null)
      .then(async resolved=>{
        if(!resolved?.slug) return null;
        const r=await fetch(api()+"/api/v1/public/business/"+encodeURIComponent(resolved.slug)+"/website");
        return r.ok?r.json():resolved;
      })
      .then(setData)
      .catch(()=>{});
  },[]);

  const c={...fallback,...(data?.content||{})};
  const business=data?.business||{};
  const number=String(c.whatsapp_number||business.whatsapp_number||"").replace(/\D/g,"");
  const whatsappMessage=encodeURIComponent("Hi SS Nutritions, I would like to know more about your wellness programs.");
  const whatsappLink=number?"https://wa.me/"+number+"?text="+whatsappMessage:"https://wa.me/?text="+whatsappMessage;
  const address=business.address||"Moinabad, Rangareddy District\nTelangana · 501504";

  const cleanupCall=useCallback(()=>{
    try{processorRef.current?.disconnect()}catch{}
    try{sourceRef.current?.disconnect()}catch{}
    try{streamRef.current?.getTracks().forEach(t=>t.stop())}catch{}
    try{socketRef.current?.close()}catch{}
    try{wakeLockRef.current?.release?.()}catch{}
    wakeLockRef.current=null;
    processorRef.current=null;
    sourceRef.current=null;
    streamRef.current=null;
    socketRef.current=null;
    nextAudioTimeRef.current=0;
  },[]);

  useEffect(()=>()=>cleanupCall(),[cleanupCall]);

  const playPcm=useCallback((base64:string)=>{
    const ctx=audioContextRef.current;
    if(!ctx) return;
    const pcm=decodeBase64Pcm16(base64);
    const buffer=ctx.createBuffer(1,pcm.length,24000);
    const channel=buffer.getChannelData(0);
    for(let i=0;i<pcm.length;i++) channel[i]=pcm[i]/32768;
    const source=ctx.createBufferSource();
    source.buffer=buffer;
    source.connect(ctx.destination);
    const now=ctx.currentTime;
    nextAudioTimeRef.current=Math.max(nextAudioTimeRef.current,now);
    source.start(nextAudioTimeRef.current);
    nextAudioTimeRef.current+=buffer.duration;
  },[]);

  const speakKnowledgeAnswer=useCallback((text:string,language:string)=>{
    if(typeof window==="undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const map:any={en:"en-IN",hi:"hi-IN",te:"te-IN",ta:"ta-IN",kn:"kn-IN",ml:"ml-IN",mr:"mr-IN",bn:"bn-IN",gu:"gu-IN",pa:"pa-IN",ur:"ur-IN"};
    const utter=new SpeechSynthesisUtterance(text);
    utter.lang=map[language]||"en-IN";
    const voices=window.speechSynthesis.getVoices();
    utter.voice=voices.find(v=>v.lang.toLowerCase()===utter.lang.toLowerCase())||voices.find(v=>v.lang.toLowerCase().startsWith(utter.lang.slice(0,2).toLowerCase()))||null;
    utter.rate=0.98;
    window.speechSynthesis.speak(utter);
  },[]);

  const startBrowserVoice=useCallback((payload:any)=>{
    const Recognition=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;
    if(!Recognition) throw new Error("Realtime calling is unavailable in this browser.");
    const recognition=new Recognition();
    recognitionRef.current=recognition;
    callActiveRef.current=true;
    recognition.continuous=true;
    recognition.interimResults=false;
    recognition.maxAlternatives=1;
    const speechLangs:any={en:"en-IN",hi:"hi-IN",te:"te-IN",ta:"ta-IN",kn:"kn-IN",ml:"ml-IN",mr:"mr-IN",bn:"bn-IN",gu:"gu-IN",pa:"pa-IN",ur:"ur-IN"};
    const browserLang=(navigator.language||"en-IN").toLowerCase();
    recognition.lang=Object.values(speechLangs).includes(browserLang)?browserLang:(speechLangs[browserLang.slice(0,2)]||"en-IN");
    setCallState("connected");
    setCallError("");

    const speakTurn=async(text:string,language:string)=>{
      speechActiveRef.current=true;
      try{recognition.stop()}catch{}
      const map:any={en:"en-IN",hi:"hi-IN",te:"te-IN",ta:"ta-IN",kn:"kn-IN",ml:"ml-IN",mr:"mr-IN",bn:"bn-IN",gu:"gu-IN",pa:"pa-IN",ur:"ur-IN"};
      if(typeof window==="undefined" || !("speechSynthesis" in window)){
        speechActiveRef.current=false;
        if(callActiveRef.current) try{recognition.start()}catch{}
        return;
      }
      window.speechSynthesis.cancel();
      await new Promise<void>(resolve=>{
        const utter=new SpeechSynthesisUtterance(text);
        utter.lang=map[language]||"en-IN";
        const voices=window.speechSynthesis.getVoices();
        utter.voice=voices.find(v=>v.lang.toLowerCase()===utter.lang.toLowerCase())||voices.find(v=>v.lang.toLowerCase().startsWith(utter.lang.slice(0,2).toLowerCase()))||null;
        utter.rate=0.98;
        utter.onend=()=>resolve();
        utter.onerror=()=>resolve();
        window.speechSynthesis.speak(utter);
      });
      speechActiveRef.current=false;
      if(callActiveRef.current) try{recognition.start()}catch{}
    };

    const greeting="Hello "+(name.trim()||"there")+", welcome to SS Nutritions. How can I help you today?";
    setTranscript([{role:"ai",text:greeting}]);

    recognition.onresult=async(event:any)=>{
      if(speechActiveRef.current || !callActiveRef.current) return;
      for(let i=event.resultIndex;i<event.results.length;i++){
        const result=event.results[i];
        if(!result.isFinal) continue;
        const text=String(result[0]?.transcript||"").trim();
        if(!text || !callActiveRef.current || speechActiveRef.current) continue;
        try{recognition.stop()}catch{}
        setTranscript(prev=>[...prev,{role:"customer",text}]);
        try{
          const rr=await fetch(api()+"/api/v1/public/business/"+encodeURIComponent(String(business.slug||"ss-nutritions"))+"/voice/turn",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({transcript:text,call_id:payload.call_id,conversation_id:conversationIdRef.current,channel:"voice"})
          });
          const answer=await rr.json();
          if(!rr.ok) throw new Error(answer.detail||"Voice answer failed.");
          conversationIdRef.current=answer.conversation_id||conversationIdRef.current;
          setTranscript(prev=>[...prev,{role:"ai",text:answer.reply}]);
          if(answer.language && speechLangs[answer.language]) recognition.lang=speechLangs[answer.language];
          if(answer.handoff_required){
            callActiveRef.current=false;
            try{recognition.stop()}catch{}
            setCallError("Our team will call you back shortly.");
            setCallState("ended");
          }else{
            await speakTurn(answer.reply,answer.language||"en");
          }
        }catch(error:any){
          setCallError(error?.message||"I could not answer that. Please try again.");
          speechActiveRef.current=false;
          if(callActiveRef.current) try{recognition.start()}catch{}
        }
      }
    };

    recognition.onerror=(event:any)=>{
      if(!callActiveRef.current) return;
      if(event?.error==="not-allowed"||event?.error==="service-not-allowed"){
        callActiveRef.current=false;
        setCallError("Microphone access is required to talk to SS Nutritions.");
        setCallState("error");
      }
    };
    recognition.onend=()=>{
      if(callActiveRef.current && !speechActiveRef.current){
        try{recognition.start()}catch{}
      }
    };
    (async()=>{
      await speakTurn(greeting,"en");
    })().catch(()=>{});

  },[business.slug,name,speakKnowledgeAnswer]);

  const connectLiveAi=useCallback(async(payload:any)=>{
    const AudioCtx=window.AudioContext||((window as any).webkitAudioContext);
    if(!AudioCtx) throw new Error("This browser does not support in-browser calling.");
    const ctx=new AudioCtx();
    audioContextRef.current=ctx;
    await ctx.resume();
    const stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true}});
    streamRef.current=stream;
    const wsUrl=api().replace(/^http:/,"ws:").replace(/^https:/,"wss:")+"/ws/public/voice/"+payload.call_id;
    const ws=new WebSocket(wsUrl);
    socketRef.current=ws;
    setCallState("connecting");
    return await new Promise<void>((resolve,reject)=>{
      let opened=false;
      ws.onopen=()=>{
        opened=true;
        setCallState("connected");
        const source=ctx.createMediaStreamSource(stream);
        const processor=ctx.createScriptProcessor(4096,1,1);
        sourceRef.current=source;
        processorRef.current=processor;
        processor.onaudioprocess=(event)=>{
          if(mutedRef.current || ws.readyState!==WebSocket.OPEN) return;
          const input=event.inputBuffer.getChannelData(0);
          ws.send(JSON.stringify({type:"audio",data:encodePcm16(input,ctx.sampleRate,16000)}));
        };
        source.connect(processor); processor.connect(ctx.destination);
        resolve();
      };
      ws.onmessage=(event)=>{
        try{
          const msg=JSON.parse(event.data);
          if(msg.type==="status" && msg.status==="ai_connected") return;
          if(msg.type==="transcript"){
            setTranscript(prev=>[...prev,{role:msg.role,text:msg.text}]);
            return;
          }
          if(msg.type==="error"){
            if(!opened) reject(new Error(msg.message||"The AI call connection failed."));
            else {setCallError(msg.message||"The AI call could not continue.");setCallState("error");}
            return;
          }
          const parts=msg?.serverContent?.modelTurn?.parts||[];
          for(const part of parts){ const data=part?.inlineData?.data; if(data) playPcm(data); }
        }catch{}
      };
      ws.onerror=()=>{
        if(!opened) reject(new Error("Realtime AI connection failed."));
        else {setCallError("The AI call connection failed.");setCallState("error");}
      };
      ws.onclose=()=>{
        if(!opened) reject(new Error("Realtime AI connection failed."));
        else if(callActiveRef.current){callActiveRef.current=false;setCallState("ended");cleanupCall();}
      };
    });
  },[cleanupCall,playPcm,requestWakeLock]);

  const startCall=async()=>{
    setCallError(""); setTranscript([]); conversationIdRef.current=null;
    if(name.trim().length<1 || phone.replace(/\D/g,"").length<5){
      setCallError("Please enter your name and mobile number first."); return;
    }
    setCallState("starting");
    callActiveRef.current=true;
    await requestWakeLock();
    try{
      const start=await fetch(api()+"/api/v1/public/business/"+encodeURIComponent(String(business.slug||"ss-nutritions"))+"/call",{
        method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:name.trim(),phone:phone.trim()})
      });
      const payload=await start.json();
      if(!start.ok) throw new Error(payload.detail||"Unable to start the call.");
      try{
        // Primary path: provider-neutral realtime AI.
        await connectLiveAi(payload);
        return;
      }catch(realtimeError){
        // Production-safe voice fallback: do not make the customer retry.
        cleanupCall();
        try{
          startBrowserVoice(payload);
          return;
        }catch(fallbackError:any){
          callActiveRef.current=false;
          setCallError(fallbackError?.message||"Voice calling is unavailable right now.");
          setCallState("error");
        }
      }
    }catch(error:any){
      callActiveRef.current=false;
      cleanupCall();
      setCallError(error?.message||"Unable to start the call.");
      setCallState("error");
    }
  };

  const endCall=()=>{
    callActiveRef.current=false;
    conversationIdRef.current=null;
    try{recognitionRef.current?.stop()}catch{}
    recognitionRef.current=null;
    try{window.speechSynthesis?.cancel()}catch{}
    try{socketRef.current?.send(JSON.stringify({type:"stop"}))}catch{}
    try{wakeLockRef.current?.release?.()}catch{}
    cleanupCall();
    setCallState("ended");
  };

  const openCall=()=>{
    setCallError("");
    setCallState("idle");
    setCallOpen(true);
  };

  const closeCall=()=>{
    endCall();
    setCallOpen(false);
  };

  return <main className="ss-page">
    <header className="ss-nav">
      <a className="ss-brand" href="#top"><span>SS</span> Nutritions</a>
      <nav><a href="#about">About</a><a href="#wellness">Wellness</a><a href="#contact">Contact</a></nav>
      <div className="ss-nav-actions">
        <button type="button" className="ss-nav-cta ss-call-outline" onClick={openCall}>☎ Call us</button>
        <a className="ss-nav-cta ss-app-link" href="/pwa/ss-nutritions">Open app</a><a className="ss-nav-cta ss-nav-wa" href={whatsappLink} target="_blank" rel="noreferrer">WhatsApp</a>
      </div>
    </header>

    <section id="top" className="ss-hero">
      <div className="ss-hero-copy">
        <p className="ss-eyebrow">{c.eyebrow}</p>
        <h1>{c.hero_title}<br/><em>{c.hero_emphasis}</em></h1>
        <p className="ss-lead">{c.hero_description}</p>
        <div className="ss-actions">
          <button type="button" className="ss-primary ss-call-button" onClick={openCall}>☎ Call us <span>↗</span></button>
          <a className="ss-secondary" href={whatsappLink} target="_blank" rel="noreferrer">WhatsApp us</a>
          <a className="ss-secondary" href="#wellness">Explore wellness</a>
        </div>
        <div className="ss-trust"><span>✓ Personal guidance</span><span>✓ Everyday wellness</span><span>✓ Organic-focused</span></div>
      </div>
      <div className="ss-hero-art" aria-label="Natural wellness illustration">
        <div className="ss-orbit ss-orbit-one"/><div className="ss-orbit ss-orbit-two"/>
        <div className="ss-leaf ss-leaf-one">🌿</div><div className="ss-leaf ss-leaf-two">🍃</div>
        <div className="ss-bowl">🥗</div><div className="ss-art-card"><strong>Small choices.</strong><span>Better everyday habits.</span></div>
      </div>
    </section>

    <section id="about" className="ss-section ss-intro"><div><p className="ss-eyebrow">OUR APPROACH</p><h2>{c.about_title}</h2></div><p>{c.about_text}</p></section>

    <section id="wellness" className="ss-section">
      <div className="ss-section-head"><div><p className="ss-eyebrow">WELLNESS AT SS</p><h2>A simpler way to work on your wellbeing.</h2></div><p>Explore the areas where we can support your journey.</p></div>
      <div className="ss-grid">
        <article><div className="ss-icon">🥗</div><h3>Nutrition guidance</h3><p>Understand everyday food choices and build practical routines around your goals.</p></article>
        <article><div className="ss-icon">🌱</div><h3>Organic-focused living</h3><p>Discover mindful ways to bring more natural, thoughtful choices into daily life.</p></article>
        <article><div className="ss-icon">🧘</div><h3>Healthy habits</h3><p>Turn small, consistent lifestyle decisions into routines you can actually maintain.</p></article>
        <article><div className="ss-icon">🤝</div><h3>Personal support</h3><p>Have a conversation about your needs and find an approach that fits your lifestyle.</p></article>
      </div>
    </section>

    <section className="ss-quote"><p>“{c.quote}”</p><span>— SS Nutritions</span></section>

    <section id="contact" className="ss-contact">
      <div><p className="ss-eyebrow">LET'S TALK</p><h2>{c.contact_heading}</h2><p>{c.contact_text}</p></div>
      <div className="ss-contact-card">
        <div><span>📍</span><div><strong>Visit / connect</strong><p>{address}</p></div></div>
        <div id="call" className="ss-contact-actions">
          <button type="button" className="ss-wa ss-call-card" onClick={openCall}>☎ Call us <span>Talk now ↗</span></button>
          <a href={whatsappLink} target="_blank" rel="noreferrer" className="ss-wa">💬 Continue on WhatsApp <span>↗</span></a>
        </div>
        
      </div>
    </section>

    <footer className="ss-footer"><strong>SS Nutritions</strong><span>Moinabad · Rangareddy · 501504</span><span>© 2026 SS Nutritions</span></footer>

    {callOpen&&<div className="ss-call-backdrop" role="dialog" aria-modal="true" aria-label="Call SS Nutritions AI">
      <div className="ss-call-modal">
        <button className="ss-call-close" type="button" onClick={closeCall} aria-label="Close">×</button>
        <h2>Talk to SS Nutritions</h2>
        <p className="ss-call-sub">Please enter your name and mobile number.</p>
        {(callState==="idle"||callState==="starting"||callState==="error")&&<div className="ss-call-form">
          <label>Name<input value={name} onChange={e=>setName(e.target.value)} placeholder="Your name" autoComplete="name"/></label>
          <label>Mobile number<input value={phone} onChange={e=>setPhone(e.target.value)} placeholder="+91 98765 43210" autoComplete="tel" inputMode="tel"/></label>
          <button type="button" className="ss-call-start" onClick={startCall} disabled={callState==="starting"}>{callState==="starting"?"Connecting…":"☎ Start call"}</button>
          {callError&&<p className="ss-call-error">{callError}</p>}
        </div>}
        {(callState==="connecting"||callState==="connected"||callState==="ended")&&<div className="ss-call-live">
          <div className={"ss-call-pulse "+(callState==="connected"?"active":"")}><span>☎</span></div>
          <strong>{callState==="connected"?"AI is listening…":callState==="connecting"?"Connecting…":"Call ended"}</strong>
          <div className="ss-transcript">{transcript.length?transcript.map((item,i)=><p key={i}><b>{item.role==="ai"?"AI":"You"}:</b> {item.text}</p>):<span>Your conversation transcript will appear here.</span>}</div>
          {callState!=="ended"&&<div className="ss-live-actions"><button type="button" onClick={()=>{setMuted(v=>{const next=!v;mutedRef.current=next;return next})}}>{muted?"Unmute":"Mute"}</button><button type="button" className="ss-end-call" onClick={endCall}>End call</button></div>}
          {callError&&<p className="ss-call-error">{callError}</p>}
        </div>}
      </div>
    </div>}
  </main>;
}
