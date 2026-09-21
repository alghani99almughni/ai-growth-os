"use client";
import {useState} from "react";
export default function Customer(){
 const [slug,setSlug]=useState("");const [tenant,setTenant]=useState<any>();const [name,setName]=useState("");const [phone,setPhone]=useState("");const [message,setMessage]=useState("");const [reply,setReply]=useState("");const [status,setStatus]=useState("");const base=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
 async function open(){const r=await fetch(base+"/api/v1/public/business/"+slug.trim().toLowerCase());const d=await r.json();if(!r.ok){setStatus(d.detail||"Business not found");return}setTenant(d);setStatus("Connected")}
 async function chat(){if(!tenant||!message)return;setReply("Thinking...");const r=await fetch(base+"/api/v1/public/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tenant_id:tenant.id,message,name,phone})});const d=await r.json();setReply(d.reply||d.detail||"Unable to answer")}
 return <main className="shell"><div className="hero"><p>CUSTOMER PWA</p><h1>{tenant?.name||"Business assistant"}</h1><p>{tenant?.description||"Ask questions, discover services and connect with the business."}</p></div>
 {!tenant?<div className="card" style={{maxWidth:600,margin:"20px auto"}}><h2>Open business</h2><input placeholder="Business slug" value={slug} onChange={e=>setSlug(e.target.value)}/><button onClick={open}>Continue</button><p>{status}</p></div>:
 <div className="grid"><div className="card"><h2>Your details</h2><input placeholder="Name" value={name} onChange={e=>setName(e.target.value)}/><input placeholder="Mobile number" value={phone} onChange={e=>setPhone(e.target.value)}/><p>{tenant.phone&&"Call: "+tenant.phone}</p><p>{tenant.whatsapp_number&&"WhatsApp: "+tenant.whatsapp_number}</p><p>{tenant.address}</p></div>
 <div className="card"><h2>AI assistant</h2><div className="chat">{reply&&<p><b>AI:</b> {reply}</p>}</div><textarea placeholder="Ask about services, prices or how to get started" value={message} onChange={e=>setMessage(e.target.value)}/><button onClick={chat}>Send</button></div></div>}
 </main>
}