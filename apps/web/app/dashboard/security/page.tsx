"use client";
import { useCallback, useEffect, useState } from "react";

type Pass = {id:string;visitor_name:string;visitor_mobile:string;purpose:string;destination:string;vehicle_number:string;status:string;created_at:string|null;expires_at:string|null;qr_token?:string|null};
const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
export default function SecurityPage(){
 const [tenantId,setTenantId]=useState(""); const [token,setToken]=useState(""); const [items,setItems]=useState<Pass[]>([]);
 const [name,setName]=useState(""); const [mobile,setMobile]=useState(""); const [verifyValue,setVerifyValue]=useState(""); const [verifyResult,setVerifyResult]=useState(""); const [purpose,setPurpose]=useState(""); const [destination,setDestination]=useState(""); const [vehicle,setVehicle]=useState(""); const [industry,setIndustry]=useState("apartment"); const [passToken,setPassToken]=useState(""); const [error,setError]=useState(""); const [busy,setBusy]=useState(false);
 const headers=()=>({"Content-Type":"application/json",Authorization:"Bearer "+token});
 const base=()=>api()+"/api/v1/tenants/"+encodeURIComponent(tenantId)+"/security";
 const load=useCallback(async()=>{if(!tenantId||!token)return;try{const r=await fetch(base()+"/passes",{headers:headers(),cache:"no-store"});const j=await r.json();if(!r.ok)throw new Error(j.detail||"Could not load visitor passes");setItems(j.items||[]);setError("")}catch(e:any){setError(e.message||"Request failed")}},[tenantId,token]);
 useEffect(()=>{try{const t=JSON.parse(localStorage.getItem("ago_tenant")||"null");if(t?.id)setTenantId(t.id)}catch{}setToken(localStorage.getItem("ago_access_token")||"")},[]);
 useEffect(()=>{load()},[load]);
 async function action(path:string,body?:unknown){setBusy(true);setError("");try{const r=await fetch(base()+path,{method:body?"POST":"POST",headers:headers(),body:body?JSON.stringify(body):undefined});const j=await r.json();if(!r.ok)throw new Error(j.detail||"Action failed");if(j.qr_token)setPassToken(j.qr_token);await load()}catch(e:any){setError(e.message||"Action failed")}finally{setBusy(false)}}
 async function create(e:React.FormEvent){e.preventDefault();await action("/passes",{visitor_name:name,visitor_mobile:mobile,purpose,destination,vehicle_number:vehicle,industry,needs_approval:true,valid_hours:24});setName("");setMobile("");setPurpose("");setDestination("");setVehicle("")}
 async function verify(){setBusy(true);setError("");setVerifyResult("");try{const r=await fetch(base()+"/verify-token",{method:"POST",headers:headers(),body:JSON.stringify({token:verifyValue})});const j=await r.json();if(!r.ok)throw new Error(j.detail||"Token verification failed");setVerifyResult("Valid pass for "+j.pass.visitor_name+" — status: "+j.pass.status);setVerifyValue("")}catch(e:any){setError(e.message||"Verification failed")}finally{setBusy(false)}}
 if(!tenantId||!token)return <main style={{padding:32}}>Please sign in to your tenant dashboard to use Security & Visitor Management.</main>;
 const input={width:"100%",padding:"10px 12px",border:"1px solid #d7dce5",borderRadius:8,marginTop:5,boxSizing:"border-box" as const};
 const button={padding:"8px 12px",border:"1px solid #d7dce5",borderRadius:8,background:"#fff",cursor:"pointer" as const};
 return <main style={{padding:24,maxWidth:1200,margin:"0 auto",color:"#17213a"}}>
 <header style={{marginBottom:22}}><h1 style={{fontSize:28,margin:0}}>Security & Visitor Management</h1><p style={{color:"#68758a"}}>Register visitors, request approval, and record secure entry and exit.</p></header>
 {error&&<div role="alert" style={{padding:12,background:"#fff1f1",color:"#a12626",borderRadius:8,marginBottom:16}}>{error}</div>}
 {verifyResult&&<div role="status" style={{padding:12,background:"#f0f8f4",color:"#176044",borderRadius:8,marginBottom:16}}>{verifyResult}</div>}
 <section style={{border:"1px solid #e1e6ee",borderRadius:12,padding:14,marginBottom:18,background:"#fff"}}><strong>Gate QR / token verification</strong><p style={{fontSize:12,color:"#68758a",margin:"5px 0 10px"}}>Paste the QR token to validate it. Verification does not grant entry; check-in remains a separate authorized action.</p><div style={{display:"flex",gap:8,flexWrap:"wrap"}}><input aria-label="Visitor QR token" value={verifyValue} onChange={e=>setVerifyValue(e.target.value)} placeholder="Paste visitor token" style={{...input,flex:"1 1 260px",marginTop:0}}/><button type="button" disabled={busy||verifyValue.trim().length<20} style={button} onClick={verify}>Verify token</button></div></section>
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
 {passToken&&<div style={{padding:10,background:"#f0f8f4",borderRadius:8,overflowWrap:"anywhere"}}><strong>Pass token (show once)</strong><div>{passToken}</div><button type="button" style={{...button,marginTop:8}} onClick={()=>navigator.clipboard?.writeText(passToken)}>Copy token</button></div>}
 </form>
 <section style={{border:"1px solid #e1e6ee",borderRadius:14,background:"#fff",overflow:"hidden"}}>
 <div style={{padding:18,display:"flex",justifyContent:"space-between",alignItems:"center"}}><h2 style={{fontSize:17,margin:0}}>Visitor passes ({items.length})</h2><button style={button} onClick={load}>Refresh</button></div>
 {items.length===0?<p style={{padding:20,color:"#68758a"}}>No visitor passes yet.</p>:<div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}><thead><tr>{["Visitor","Purpose / destination","Vehicle","Status","Actions"].map(x=><th key={x} style={{textAlign:"left",padding:12,background:"#f7f9fc",borderTop:"1px solid #edf0f5"}}>{x}</th>)}</tr></thead><tbody>{items.map(p=><tr key={p.id}><td style={{padding:12,borderTop:"1px solid #edf0f5"}}><strong>{p.visitor_name}</strong><div style={{color:"#68758a"}}>{p.visitor_mobile}</div></td><td style={{padding:12,borderTop:"1px solid #edf0f5"}}>{p.purpose}<div style={{color:"#68758a"}}>{p.destination}</div></td><td style={{padding:12,borderTop:"1px solid #edf0f5"}}>{p.vehicle_number||"—"}</td><td style={{padding:12,borderTop:"1px solid #edf0f5"}}>{p.status}</td><td style={{padding:12,borderTop:"1px solid #edf0f5",whiteSpace:"nowrap"}}><div style={{display:"flex",gap:5,flexWrap:"wrap"}}>{p.status==="pending"&&<button style={button} disabled={busy} onClick={()=>action("/passes/"+p.id+"/approve")}>Approve</button>}{p.status==="approved"&&<button style={button} disabled={busy} onClick={()=>action("/passes/"+p.id+"/check-in")}>Check in</button>}{p.status==="checked_in"&&<button style={button} disabled={busy} onClick={()=>action("/passes/"+p.id+"/check-out")}>Check out</button>}</div></td></tr>)}</tbody></table></div>}
 </section></div></main>
}
