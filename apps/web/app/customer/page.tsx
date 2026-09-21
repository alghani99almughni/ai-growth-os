"use client";
import {useEffect,useRef,useState} from "react";
type Tenant={id:string;name:string;slug:string;industry?:string;description?:string;address?:string};
type Msg={who:string;text:string};
export default function Customer(){
 const [slug,setSlug]=useState(""); const [tenant,setTenant]=useState<Tenant|null>(null);
 const [name,setName]=useState(""); const [phone,setPhone]=useState(""); const [status,setStatus]=useState("");
 const [calling,setCalling]=useState(false); const [messages,setMessages]=useState<Msg[]>([]);
 const [message,setMessage]=useState(""); const recognitionRef=useRef<any>(null);
 const base=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
 async function open(){const r=await fetch(base+"/api/v1/public/business/"+slug.trim().toLowerCase());const d=await r.json();if(!r.ok){setStatus(d.detail||"Business not found");return}setTenant(d);setStatus("Ready");}
 function speak(text:string){if(typeof window!=="undefined"&&"speechSynthesis" in window){window.speechSynthesis.cancel();window.speechSynthesis.speak(new SpeechSynthesisUtterance(text));}}
 async function startCall(){
  if(!tenant||!name.trim()||!phone.trim()){setStatus("Please confirm your name and mobile number first.");return}
  setCalling(true);setStatus("Connecting to AI...");
  try{await navigator.mediaDevices.getUserMedia({audio:true});
   const r=await fetch(base+"/api/v1/public/business/"+tenant.slug+"/call",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,phone})});
   const d=await r.json();if(!r.ok)throw new Error(d.detail||"Unable to start call");
   setStatus("AI connected");setMessages([{who:"AI",text:d.greeting}]);speak(d.greeting);startListening(d.call_id);
  }catch(e:any){setCalling(false);setStatus(e.message||"Microphone access is required.");}
 }
 function startListening(callId:string){
  const SR=(window as any).SpeechRecognition||(window as any).webkitSpeechRecognition;
  if(!SR){setStatus("AI connected. This browser does not support voice recognition; use the text assistant below.");return}
  const rec=new SR();recognitionRef.current=rec;rec.lang="en-IN";rec.continuous=true;rec.interimResults=false;
  rec.onresult=async(e:any)=>{const text=e.results[e.results.length-1][0].transcript;setMessages(m=>[...m,{who:"You",text}]);const r=await fetch(base+"/api/v1/public/business/"+tenant!.slug+"/voice/turn",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({transcript:text,call_id:callId,channel:"voice"})});const d=await r.json();if(d.reply){setMessages(m=>[...m,{who:"AI",text:d.reply}]);speak(d.reply);}};
  rec.onerror=()=>setStatus("Voice recognition paused.");rec.onend=()=>{if(calling)try{rec.start()}catch{}};rec.start();
 }
 function endCall(){setCalling(false);setStatus("Call ended");try{recognitionRef.current?.stop()}catch{};window.speechSynthesis?.cancel();}
 async function chat(){if(!tenant||!message)return;const r=await fetch(base+"/api/v1/public/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tenant_id:tenant.id,message,name,phone,channel:"pwa"})});const d=await r.json();setMessages(m=>[...m,{who:"You",text:message},{who:"AI",text:d.reply||d.detail||"Unable to answer"}]);setMessage("");}
 useEffect(()=>()=>{try{recognitionRef.current?.stop()}catch{}},[]);
 return <main className="shell"><div className="hero"><p>CUSTOMER PWA • AI VOICE</p><h1>{tenant?.name||"Business assistant"}</h1><p>{tenant?.description||"Connect instantly with the business AI assistant."}</p></div>
 {!tenant?<div className="card" style={{maxWidth:600,margin:"20px auto"}}><h2>Open business</h2><input placeholder="Business slug" value={slug} onChange={e=>setSlug(e.target.value)}/><button onClick={open}>Continue</button><p>{status}</p></div>:
 <div className="grid"><div className="card"><h2>📞 Call {tenant.name}</h2><p>One tap connects you to the AI assistant. The business mobile number is not displayed.</p><input placeholder="Your name" value={name} onChange={e=>setName(e.target.value)}/><input placeholder="Your mobile number" inputMode="tel" value={phone} onChange={e=>setPhone(e.target.value)}/>{!calling?<button onClick={startCall}>📞 Call now</button>:<button onClick={endCall}>🔴 End call</button>}<p>{status}</p><p>{tenant.address}</p></div>
 <div className="card"><h2>{calling?"AI Voice Conversation":"AI Assistant"}</h2><div className="chat">{messages.map((m,i)=><p key={i}><b>{m.who}:</b> {m.text}</p>)}</div>{!calling&&<><textarea placeholder="Ask about services, prices or bookings" value={message} onChange={e=>setMessage(e.target.value)}/><button onClick={chat}>Send</button></>}</div></div>}
 </main>
}