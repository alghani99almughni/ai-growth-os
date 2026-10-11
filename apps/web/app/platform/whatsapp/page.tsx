"use client";
import { useCallback, useEffect, useState } from "react";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
type Row = { tenant_id:string; tenant_name:string; tenant_slug:string; industry:string; status:string; openwa_connected:boolean; openwa_status:string|null; openwa_phone:string|null; meta_connected:boolean; meta_status:string|null; meta_phone:string|null; priority:string; active:string|null };
type Overview = { totals:{tenants:number;with_openwa:number;with_meta:number;with_any_channel:number}; items:Row[] };
const card:React.CSSProperties={background:"#fff",border:"1px solid #e8ecf3",borderRadius:14,padding:18};
const input:React.CSSProperties={display:"block",width:"100%",marginTop:6,padding:"10px 12px",border:"1px solid #d7dce5",borderRadius:8,fontSize:13,boxSizing:"border-box"};
const btn:React.CSSProperties={background:"#fff",border:"1px solid #d7dce5",color:"#17213a",padding:"8px 12px",borderRadius:8,fontSize:12,fontWeight:650,cursor:"pointer",marginRight:6,marginTop:4};
export default function PlatformWhatsAppPage(){
 const [data,setData]=useState<Overview|null>(null); const [loading,setLoading]=useState(true);
 const [error,setError]=useState(""); const [notice,setNotice]=useState("");
 const [configFor,setConfigFor]=useState<Row|null>(null); const [sendFor,setSendFor]=useState<Row|null>(null);
 const token=()=>typeof window==="undefined"?"":localStorage.getItem("ago_access_token")||"";
 const load=useCallback(async()=>{setLoading(true);setError("");try{
   const r=await fetch(API+"/api/v1/platform/whatsapp/overview",{headers:{Authorization:"Bearer "+token()},cache:"no-store"});
   const x=await r.json().catch(()=>({})); if(!r.ok)throw new Error(x.detail||"HTTP "+r.status); setData(x);
 }catch(e:any){setError(e.message||"Could not load WhatsApp status");}finally{setLoading(false);}},[]);
 useEffect(()=>{if(!token()){window.location.href="/login";return;}void load();},[load]);
 async function disconnect(row:Row,provider:"openwa"|"meta"){
   if(!window.confirm("Disconnect "+provider+" for "+row.tenant_name+"?"))return;
   setError("");setNotice("");
   try{const r=await fetch(API+"/api/v1/platform/tenants/"+row.tenant_id+"/whatsapp/disconnect?provider="+provider,{method:"POST",headers:{Authorization:"Bearer "+token()}});
    const x=await r.json().catch(()=>({}));if(!r.ok)throw new Error(x.detail||"Disconnect failed");setNotice(provider+" disconnected for "+row.tenant_name);await load();
   }catch(e:any){setError(e.message||"Disconnect failed");}
 }
 async function priority(row:Row,value:"openwa"|"meta"){
   try{const r=await fetch(API+"/api/v1/platform/tenants/"+row.tenant_id+"/whatsapp/priority",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+token()},body:JSON.stringify({priority:value})});
    const x=await r.json().catch(()=>({}));if(!r.ok)throw new Error(x.detail||"Priority update failed");setNotice("Preferred channel updated for "+row.tenant_name);await load();
   }catch(e:any){setError(e.message||"Priority update failed");}
 }
 if(loading)return <div style={{padding:60,textAlign:"center",color:"#75839a"}}>Loading WhatsApp status…</div>;
 return <div style={{color:"#17213a"}}>
  <div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"flex-start",flexWrap:"wrap",marginBottom:22}}>
   <div><p style={{margin:"0 0 8px",color:"#625ff0",fontSize:11,fontWeight:800,letterSpacing:".12em"}}>SUPER ADMIN / COMMUNICATIONS</p><h1 style={{margin:0,fontSize:27}}>WhatsApp across all tenants</h1><p style={{margin:"7px 0 0",color:"#75839a",fontSize:13}}>Configure OpenWA or Meta Cloud, select the preferred channel, and send a test message for a specific tenant.</p></div>
   <button onClick={()=>void load()} style={btn}>Refresh status</button>
  </div>
  {error&&<div role="alert" style={{...card,borderColor:"#f1bcbc",color:"#b42323",marginBottom:12}}>{error}</div>}
  {notice&&<div role="status" style={{...card,borderColor:"#bcebd5",color:"#16774d",marginBottom:12}}>{notice}</div>}
  <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(170px,1fr))",gap:12,marginBottom:20}}>
   <Kpi label="Tenants" value={data?.totals.tenants||0}/><Kpi label="OpenWA connected" value={data?.totals.with_openwa||0}/><Kpi label="Meta connected" value={data?.totals.with_meta||0}/><Kpi label="Any channel" value={data?.totals.with_any_channel||0}/>
  </div>
  {!data?.items.length?<div style={card}>No tenants found.</div>:<div style={{...card,padding:0,overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:13,minWidth:900}}>
   <thead style={{background:"#fafbfd"}}><tr>{["Tenant","OpenWA","Meta Cloud API","Preferred","Actions"].map(h=><th key={h} style={{textAlign:"left",padding:"12px 14px",fontSize:10,color:"#8490a4",textTransform:"uppercase",letterSpacing:".06em",borderBottom:"1px solid #edf0f5"}}>{h}</th>)}</tr></thead>
   <tbody>{data.items.map(row=><tr key={row.tenant_id} style={{borderTop:"1px solid #f1f4f8"}}>
    <td style={{padding:14}}><strong>{row.tenant_name}</strong><div style={{fontSize:11,color:"#8490a4"}}>/{row.tenant_slug} · {row.industry}</div><div style={{fontSize:11,color:"#8490a4"}}>Tenant status: {row.status}</div></td>
    <td style={{padding:14}}><Status connected={row.openwa_connected} status={row.openwa_status} phone={row.openwa_phone}/></td>
    <td style={{padding:14}}><Status connected={row.meta_connected} status={row.meta_status} phone={row.meta_phone}/></td>
    <td style={{padding:14}}><select value={row.priority==="meta"?"meta":"openwa"} onChange={e=>void priority(row,e.target.value as "openwa"|"meta")} style={{...input,marginTop:0,width:130}}><option value="openwa">OpenWA first</option><option value="meta">Meta first</option></select></td>
    <td style={{padding:14,whiteSpace:"nowrap"}}><button style={btn} onClick={()=>setConfigFor(row)}>Configure</button><button style={btn} onClick={()=>setSendFor(row)}>Send test</button>{row.openwa_connected&&<button style={btn} onClick={()=>void disconnect(row,"openwa")}>Disconnect OpenWA</button>}{row.meta_connected&&<button style={btn} onClick={()=>void disconnect(row,"meta")}>Disconnect Meta</button>}</td>
   </tr>)}</tbody></table></div>}
  {configFor&&<ConfigureModal row={configFor} onClose={()=>setConfigFor(null)} onSaved={async()=>{setConfigFor(null);setNotice("WhatsApp configuration saved.");await load();}}/>}
  {sendFor&&<SendModal row={sendFor} onClose={()=>setSendFor(null)} onSent={async()=>{setSendFor(null);setNotice("WhatsApp send request accepted.");await load();}}/>}
 </div>;
}
function Status({connected,status,phone}:{connected:boolean;status:string|null;phone:string|null}){return <div><span style={{display:"inline-block",padding:"4px 8px",borderRadius:20,fontSize:10,fontWeight:800,background:connected?"#e9faf2":"#f2f4f8",color:connected?"#1d9c68":"#6b7686"}}>{connected?"CONNECTED":(status||"DISCONNECTED").toUpperCase()}</span>{phone&&<div style={{fontSize:11,color:"#75839a",marginTop:5}}>{phone}</div>}</div>}
function ConfigureModal({row,onClose,onSaved}:{row:Row;onClose:()=>void;onSaved:()=>void}){
 const [provider,setProvider]=useState<"openwa"|"meta">("openwa");const [baseUrl,setBaseUrl]=useState("");const [apiKey,setApiKey]=useState("");const [sessionId,setSessionId]=useState("");const [accessToken,setAccessToken]=useState("");const [phoneId,setPhoneId]=useState("");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
 async function submit(){setBusy(true);setError("");try{
  const body=provider==="openwa"?{provider,base_url:baseUrl.trim(),api_key:apiKey,session_id:sessionId.trim()}:{provider,access_token:accessToken,phone_number_id:phoneId.trim()};
  const r=await fetch(API+"/api/v1/platform/tenants/"+row.tenant_id+"/whatsapp/configure",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+(localStorage.getItem("ago_access_token")||"")},body:JSON.stringify(body)});
  const x=await r.json().catch(()=>({}));if(!r.ok)throw new Error(x.detail||"Configuration failed");onSaved();
 }catch(e:any){setError(e.message||"Configuration failed");}finally{setBusy(false);}}
 return <Modal title={"Configure WhatsApp · "+row.tenant_name} onClose={onClose}>
  <label style={label}>Provider<select value={provider} onChange={e=>setProvider(e.target.value as any)} style={input}><option value="openwa">OpenWA</option><option value="meta">Meta WhatsApp Cloud API</option></select></label>
  {provider==="openwa"?<><label style={label}>OpenWA base URL<input value={baseUrl} onChange={e=>setBaseUrl(e.target.value)} placeholder="https://your-openwa-service" style={input}/></label><label style={label}>API key<input type="password" value={apiKey} onChange={e=>setApiKey(e.target.value)} style={input}/></label><label style={label}>Session ID<input value={sessionId} onChange={e=>setSessionId(e.target.value)} style={input}/></label></>:<><label style={label}>Meta access token<input type="password" value={accessToken} onChange={e=>setAccessToken(e.target.value)} style={input}/></label><label style={label}>WhatsApp phone number ID<input value={phoneId} onChange={e=>setPhoneId(e.target.value)} style={input}/></label></>}
  {error&&<p role="alert" style={{color:"#b42323",fontSize:12}}>{error}</p>}<div style={{display:"flex",gap:8,marginTop:16}}><button disabled={busy} onClick={()=>void submit()} style={{...btn,background:"#5b5cf0",color:"#fff",border:0}}>{busy?"Validating…":"Validate & save"}</button><button onClick={onClose} style={btn}>Cancel</button></div>
 </Modal>;
}
function SendModal({row,onClose,onSent}:{row:Row;onClose:()=>void;onSent:()=>void}){
 const [phone,setPhone]=useState("");const [message,setMessage]=useState("Test message from AI Growth OS.");const [busy,setBusy]=useState(false);const [error,setError]=useState("");
 async function submit(){setBusy(true);setError("");try{const r=await fetch(API+"/api/v1/platform/tenants/"+row.tenant_id+"/whatsapp/send",{method:"POST",headers:{"Content-Type":"application/json",Authorization:"Bearer "+(localStorage.getItem("ago_access_token")||"")},body:JSON.stringify({phone:phone.trim(),text:message.trim()})});const x=await r.json().catch(()=>({}));if(!r.ok)throw new Error(x.detail||"Send failed");onSent();}catch(e:any){setError(e.message||"Send failed");}finally{setBusy(false);}}
 return <Modal title={"Send WhatsApp · "+row.tenant_name} onClose={onClose}><p style={{fontSize:12,color:"#75839a",marginTop:0}}>This sends a real message through the tenant's configured active channel.</p><label style={label}>Recipient phone<input value={phone} onChange={e=>setPhone(e.target.value)} placeholder="+91..." style={input}/></label><label style={label}>Message<textarea rows={4} value={message} onChange={e=>setMessage(e.target.value)} style={input}/></label>{error&&<p role="alert" style={{color:"#b42323",fontSize:12}}>{error}</p>}<div style={{display:"flex",gap:8,marginTop:16}}><button disabled={busy||!phone.trim()||!message.trim()} onClick={()=>void submit()} style={{...btn,background:"#5b5cf0",color:"#fff",border:0}}>{busy?"Sending…":"Send message"}</button><button onClick={onClose} style={btn}>Cancel</button></div></Modal>;
}
function Modal({title,children,onClose}:{title:string;children:React.ReactNode;onClose:()=>void}){return <div onClick={onClose} style={{position:"fixed",inset:0,background:"rgba(7,21,46,.55)",zIndex:100,display:"grid",placeItems:"center",padding:20}}><div onClick={e=>e.stopPropagation()} style={{background:"#fff",borderRadius:14,padding:24,width:"100%",maxWidth:540,maxHeight:"90vh",overflow:"auto"}}><h3 style={{margin:"0 0 16px",fontSize:16}}>{title}</h3>{children}</div></div>}
function Kpi({label,value}:{label:string;value:number}){return <div style={card}><div style={{fontSize:10,color:"#8490a4",textTransform:"uppercase",letterSpacing:".08em",fontWeight:700}}>{label}</div><div style={{fontSize:25,fontWeight:750,marginTop:5}}>{value}</div></div>}
const label:React.CSSProperties={display:"block",marginTop:10,fontSize:11,color:"#8490a4",textTransform:"uppercase",letterSpacing:".06em",fontWeight:700};
