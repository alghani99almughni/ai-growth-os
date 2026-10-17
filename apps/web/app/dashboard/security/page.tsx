"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Pass = {id:string;visitor_name:string;visitor_mobile:string;purpose:string;destination:string;vehicle_number:string;status:string;created_at:string|null;expires_at:string|null;qr_token?:string|null};
const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
export default function SecurityPage(){
 const [tenantId,setTenantId]=useState(""); const [token,setToken]=useState(""); const [items,setItems]=useState<Pass[]>([]); const [entryQrUrl,setEntryQrUrl]=useState(""); const [entryQrImage,setEntryQrImage]=useState(""); const [entryQrError,setEntryQrError]=useState("");
 const [name,setName]=useState(""); const [mobile,setMobile]=useState(""); const [verifyValue,setVerifyValue]=useState(""); const [verifyResult,setVerifyResult]=useState(""); const [purpose,setPurpose]=useState(""); const [destination,setDestination]=useState(""); const [vehicle,setVehicle]=useState(""); const [industry,setIndustry]=useState("apartment"); const [passToken,setPassToken]=useState(""); const [qrImage,setQrImage]=useState(""); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
 const [cameraOpen,setCameraOpen]=useState(false); const [cameraMessage,setCameraMessage]=useState(""); const [search,setSearch]=useState(""); const [statusFilter,setStatusFilter]=useState("all"); const videoRef=useRef<HTMLVideoElement|null>(null); const streamRef=useRef<MediaStream|null>(null); const scanFrameRef=useRef<number|null>(null);
 const headers=()=>({"Content-Type":"application/json",Authorization:"Bearer "+token});
 const filteredItems=useMemo(()=>items.filter(p=>{
  const statusMatches=statusFilter==="all"||p.status===statusFilter;
  const needle=search.trim().toLowerCase();
  const textMatches=!needle||[p.visitor_name,p.visitor_mobile,p.purpose,p.destination,p.vehicle_number,p.status].some(v=>String(v||"").toLowerCase().includes(needle));
  return statusMatches&&textMatches;
 }),[items,search,statusFilter]);
 const counts=useMemo(()=>({pending:items.filter(p=>p.status==="pending").length,approved:items.filter(p=>p.status==="approved").length,inside:items.filter(p=>p.status==="checked_in").length,closed:items.filter(p=>["checked_out","denied","expired","cancelled"].includes(p.status)).length}),[items]);
 const base=()=>api()+"/api/v1/tenants/"+encodeURIComponent(tenantId)+"/security";
 const load=useCallback(async()=>{if(!tenantId||!token)return;try{const r=await fetch(base()+"/passes",{headers:headers(),cache:"no-store"});const j=await r.json();if(!r.ok)throw new Error(j.detail||"Could not load visitor passes");setItems(j.items||[]);setError("")}catch(e:any){setError(e.message||"Request failed")}},[tenantId,token]);
 useEffect(()=>{try{const t=JSON.parse(localStorage.getItem("ago_tenant")||"null");if(t?.id)setTenantId(t.id)}catch{}setToken(localStorage.getItem("ago_access_token")||"")},[]);
 useEffect(()=>{load()},[load]);
 useEffect(()=>()=>{if(streamRef.current)streamRef.current.getTracks().forEach(t=>t.stop());if(scanFrameRef.current!==null)cancelAnimationFrame(scanFrameRef.current)},[]);
 async function action(path:string,body?:unknown){setBusy(true);setError("");try{const r=await fetch(base()+path,{method:body?"POST":"POST",headers:headers(),body:body?JSON.stringify(body):undefined});const j=await r.json();if(!r.ok)throw new Error(j.detail||"Action failed");if(j.qr_token)setPassToken(j.qr_token);await load()}catch(e:any){setError(e.message||"Action failed")}finally{setBusy(false)}}
 async function create(e:React.FormEvent){e.preventDefault();await action("/passes",{visitor_name:name,visitor_mobile:mobile,purpose,destination,vehicle_number:vehicle,industry,needs_approval:true,valid_hours:24});setName("");setMobile("");setPurpose("");setDestination("");setVehicle("")}
 async function renderQr(){setBusy(true);setError("");try{const r=await fetch(base()+"/qr",{method:"POST",headers:headers(),body:JSON.stringify({token:passToken})});const j=await r.json();if(!r.ok)throw new Error(j.detail||"QR generation failed");setQrImage(j.image_data_url)}catch(e:any){setError(e.message||"QR generation failed")}finally{setBusy(false)}}
 async function loadEntryQr(){setBusy(true);setEntryQrError("");try{const r=await fetch(base()+"/entry-qr",{headers:headers(),cache:"no-store"});const j=await r.json();if(!r.ok)throw new Error(j.detail||"Could not generate visitor registration QR");setEntryQrUrl(j.entry_url);setEntryQrImage(j.image_data_url)}catch(e:any){setEntryQrError(e.message||"Could not generate visitor registration QR")}finally{setBusy(false)}}
 function exportVisitorRegister(){
  // Export only the records already authorized and loaded for this tenant.
  const cols:[keyof Pass,string][]=[["visitor_name","Visitor name"],["visitor_mobile","Mobile"],["purpose","Purpose"],["destination","Host / destination"],["vehicle_number","Vehicle"],["status","Status"],["created_at","Created at"],["expires_at","Expires at"]];
  const cell=(v:unknown)=>{const s=String(v??"");return '"'+s.replace(/"/g,'""')+'"';};
  const csv=[cols.map(([,label])=>cell(label)).join(","),...filteredItems.map(p=>cols.map(([key])=>cell(p[key])).join(","))].join("\\r\\n");
  const blob=new Blob(["\\uFEFF",csv],{type:"text/csv;charset=utf-8;"});
  const url=URL.createObjectURL(blob);const a=document.createElement("a");
  a.href=url;a.download="visitor-register-"+new Date().toISOString().slice(0,10)+".csv";
  document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
 }
 function stopCamera(){
  if(scanFrameRef.current!==null){cancelAnimationFrame(scanFrameRef.current);scanFrameRef.current=null;}
  if(streamRef.current){streamRef.current.getTracks().forEach(t=>t.stop());streamRef.current=null;}
  if(videoRef.current)videoRef.current.srcObject=null;
  setCameraOpen(false);
 }
 async function startCamera(){
  setCameraMessage("");
  if(!navigator.mediaDevices?.getUserMedia){setCameraMessage("Camera access requires HTTPS and a supported browser.");return;}
  const Detector=(window as any).BarcodeDetector;
  if(!Detector){setCameraMessage("This browser does not support built-in QR scanning. Paste the token below instead.");return;}
  try{
   const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:"environment"}},audio:false});
   streamRef.current=stream;setCameraOpen(true);
   await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
   const video=videoRef.current;
   if(!video){stream.getTracks().forEach(t=>t.stop());streamRef.current=null;return;}
   video.srcObject=stream;await video.play();
   const detector=new Detector({formats:["qr_code"]});
   const scan=async()=>{
    if(!streamRef.current||!videoRef.current)return;
    try{
     const codes=await detector.detect(videoRef.current);
     const raw=codes?.[0]?.rawValue;
     if(raw){
      let tokenValue=raw;
      try{const u=new URL(raw);tokenValue=u.searchParams.get("token")||u.searchParams.get("qr")||u.pathname.split("/").filter(Boolean).pop()||raw;}catch{}
      setVerifyValue(tokenValue);setCameraMessage("QR captured. Select Verify token to check its status.");stopCamera();return;
     }
    }catch{}
    scanFrameRef.current=requestAnimationFrame(scan);
   };
   scanFrameRef.current=requestAnimationFrame(scan);
  }catch(e:any){setCameraMessage(e.message||"Unable to open camera.");stopCamera();}
 }
 async function verify(){setBusy(true);setError("");setVerifyResult("");try{const r=await fetch(base()+"/verify-token",{method:"POST",headers:headers(),body:JSON.stringify({token:verifyValue})});const j=await r.json();if(!r.ok)throw new Error(j.detail||"Token verification failed");const verifiedPass=j?.pass??j;if(j?.valid===false||typeof verifiedPass?.visitor_name!=="string"||typeof verifiedPass?.status!=="string")throw new Error("Verification response was incomplete. Refresh and try again.");setVerifyResult("Valid pass for "+verifiedPass.visitor_name+" — status: "+verifiedPass.status);setVerifyValue("")}catch(e:any){setError(e.message||"Verification failed")}finally{setBusy(false)}}
 if(!tenantId||!token)return <main style={{padding:32}}>Please sign in to your tenant dashboard to use Security & Visitor Management.</main>;
 const input={width:"100%",padding:"10px 12px",border:"1px solid #d7dce5",borderRadius:8,marginTop:5,boxSizing:"border-box" as const};
 const button={padding:"8px 12px",border:"1px solid #d7dce5",borderRadius:8,background:"#fff",cursor:"pointer" as const};
 return <main style={{padding:24,maxWidth:1200,margin:"0 auto",color:"#17213a"}}>
 <header style={{marginBottom:22}}><h1 style={{fontSize:28,margin:0}}>Security & Visitor Management</h1><p style={{color:"#68758a"}}>Register visitors, request approval, and record secure entry and exit.</p></header>
 {error&&<div role="alert" style={{padding:12,background:"#fff1f1",color:"#a12626",borderRadius:8,marginBottom:16}}>{error}</div>}
 {verifyResult&&<div role="status" style={{padding:12,background:"#f0f8f4",color:"#176044",borderRadius:8,marginBottom:16}}>{verifyResult}</div>}
 <section style={{border:"1px solid #e1e6ee",borderRadius:12,padding:14,marginBottom:18,background:"#fff"}}><strong>Visitor self-registration QR</strong><p style={{fontSize:12,color:"#68758a",margin:"6px 0 10px"}}>Visitors can scan this QR and submit their details in the browser. PWA installation is optional; every request still requires staff approval.</p><button type="button" style={button} disabled={busy} onClick={loadEntryQr}>Generate registration QR</button>{entryQrError&&<p role="alert" style={{fontSize:12,color:"#b42318"}}>{entryQrError}</p>}{entryQrImage&&<div style={{display:"flex",gap:14,alignItems:"center",flexWrap:"wrap",marginTop:12}}><img src={entryQrImage} alt="QR code for visitor self-registration" width={180} height={180}/><div style={{fontSize:12,overflowWrap:"anywhere",maxWidth:420}}><a href={entryQrUrl} target="_blank" rel="noreferrer">{entryQrUrl}</a><p style={{color:"#68758a"}}>Print or share this QR at the entrance. Registration is stored in SmartCheck and does not authorize entry.</p></div></div>}</section>
 <section style={{border:"1px solid #e1e6ee",borderRadius:12,padding:14,marginBottom:18,background:"#fff"}}><strong>Gate QR / token verification</strong>
 <div style={{display:"flex",gap:8,flexWrap:"wrap",margin:"8px 0"}}><button type="button" style={button} disabled={busy||cameraOpen} onClick={startCamera}>Open camera to scan QR</button>{cameraOpen&&<button type="button" style={button} onClick={stopCamera}>Stop camera</button>}</div>
 {cameraOpen&&<video ref={videoRef} muted playsInline style={{display:"block",width:"100%",maxWidth:420,maxHeight:320,background:"#111",borderRadius:8,marginBottom:8}}/>}
 {cameraMessage&&<p role="status" style={{fontSize:13,color:"#68758a"}}>{cameraMessage}</p>}<p style={{fontSize:12,color:"#68758a",margin:"5px 0 10px"}}>Paste the QR token to validate it. Verification does not grant entry; check-in remains a separate authorized action.</p><div style={{display:"flex",gap:8,flexWrap:"wrap"}}><input aria-label="Visitor QR token" value={verifyValue} onChange={e=>setVerifyValue(e.target.value)} placeholder="Paste visitor token" style={{...input,flex:"1 1 260px",marginTop:0}}/><button type="button" disabled={busy||verifyValue.trim().length<20} style={button} onClick={verify}>Verify token</button></div></section>
 <div style={{display:"grid",gridTemplateColumns:"minmax(280px,360px) 1fr",gap:20,alignItems:"start"}}>
 <form onSubmit={create} style={{border:"1px solid #e1e6ee",borderRadius:14,padding:18,background:"#fff"}}>
 <h2 style={{fontSize:17,marginTop:0}}>Register visitor</h2>
 <label>Industry template<select value={industry} onChange={e=>setIndustry(e.target.value)} style={input}><option value="school">School</option><option value="apartment">Apartment</option><option value="hospital">Hospital</option></select></label>
 <label style={{display:"block",marginTop:12}}>Visitor name<input required value={name} onChange={e=>setName(e.target.value)} style={input} maxLength={160}/></label>
 <label style={{display:"block",marginTop:12}}>Mobile<input value={mobile} onChange={e=>setMobile(e.target.value)} style={input} maxLength={32}/></label>
 <label style={{display:"block",marginTop:12}}>Purpose<input value={purpose} onChange={e=>setPurpose(e.target.value)} style={input} maxLength={240}/></label>
 <label style={{display:"block",marginTop:12}}>Host / department / destination<input value={destination} onChange={e=>setDestination(e.target.value)} style={input} maxLength={240}/></label>
 <label style={{display:"block",marginTop:12}}>Vehicle number<input value={vehicle} onChange={e=>setVehicle(e.target.value)} style={input} maxLength={40}/></label>
 <button disabled={busy} style={{...button,marginTop:16,background:"#17213a",color:"#fff",width:"100%"}}>{busy?"Saving…":"Create pass (approval required)"}</button>
 <p style={{fontSize:12,color:"#68758a"}}>The pass starts pending and cannot be used for entry until an authorized user approves it.</p>
 {passToken&&<div style={{padding:10,background:"#f0f8f4",borderRadius:8,overflowWrap:"anywhere"}}><strong>Pass token (show once)</strong><div>{passToken}</div><div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:8}}><button type="button" style={button} onClick={()=>navigator.clipboard?.writeText(passToken)}>Copy token</button><button type="button" style={button} disabled={busy} onClick={renderQr}>Generate QR</button></div>{qrImage&&<div style={{marginTop:10}}><img src={qrImage} alt="Visitor pass QR code" width={180} height={180}/><button type="button" style={{...button,display:"block",marginTop:6}} onClick={()=>{setQrImage("");setPassToken("")}}>Hide QR and token</button></div>}</div>}
 </form>
 <section style={{border:"1px solid #e1e6ee",borderRadius:14,background:"#fff",overflow:"hidden"}}>
 <div style={{padding:18,display:"flex",justifyContent:"space-between",alignItems:"center",gap:8,flexWrap:"wrap"}}><h2 style={{fontSize:17,margin:0}}>Visitor passes ({items.length})</h2><div style={{display:"flex",gap:8,flexWrap:"wrap"}}><button style={button} onClick={exportVisitorRegister} disabled={!filteredItems.length}>Export Excel / CSV</button><button style={button} onClick={load}>Refresh</button></div></div>
 {items.length===0?<p style={{padding:20,color:"#68758a"}}>No visitor passes yet.</p>:<div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}><thead><tr>{["Visitor","Purpose / destination","Vehicle","Status","Actions"].map(x=><th key={x} style={{textAlign:"left",padding:12,background:"#f7f9fc",borderTop:"1px solid #edf0f5"}}>{x}</th>)}</tr></thead><tbody>{filteredItems.map(p=><tr key={p.id}><td style={{padding:12,borderTop:"1px solid #edf0f5"}}><strong>{p.visitor_name}</strong><div style={{color:"#68758a"}}>{p.visitor_mobile}</div></td><td style={{padding:12,borderTop:"1px solid #edf0f5"}}>{p.purpose}<div style={{color:"#68758a"}}>{p.destination}</div></td><td style={{padding:12,borderTop:"1px solid #edf0f5"}}>{p.vehicle_number||"—"}</td><td style={{padding:12,borderTop:"1px solid #edf0f5"}}>{p.status}</td><td style={{padding:12,borderTop:"1px solid #edf0f5",whiteSpace:"nowrap"}}><div style={{display:"flex",gap:5,flexWrap:"wrap"}}>{p.status==="pending"&&<><button style={button} disabled={busy} onClick={()=>action("/passes/"+p.id+"/approve")}>Approve</button><button style={{...button,borderColor:"#fda29b",color:"#b42318"}} disabled={busy} onClick={()=>{if(window.confirm("Deny this visitor request?"))action("/passes/"+p.id+"/deny")}}>Deny</button></>}{p.status==="approved"&&<><button style={button} disabled={busy} onClick={()=>action("/passes/"+p.id+"/check-in")}>Check in</button><button style={{...button,borderColor:"#fda29b",color:"#b42318"}} disabled={busy} onClick={()=>{if(window.confirm("Cancel this visitor pass?"))action("/passes/"+p.id+"/cancel")}}>Cancel pass</button></>}{p.status==="checked_in"&&<button style={button} disabled={busy} onClick={()=>action("/passes/"+p.id+"/check-out")}>Check out</button>}</div></td></tr>)}</tbody></table></div>}
 </section></div></main>
}
