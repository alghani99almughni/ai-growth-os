"use client";
import { useCallback, useEffect, useState } from "react";
import { Bell, Check, X } from "lucide-react";
const API=(process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000").replace(/\/$/,"");
type Alert={id:string;event_type:string;title:string;message:string;payload?:Record<string,unknown>;read:boolean;created_at:string};
export default function OperationalAlertsBell(){
 const [token,setToken]=useState(""); const [items,setItems]=useState<Alert[]>([]); const [open,setOpen]=useState(false); const [error,setError]=useState("");
 const load=useCallback(async()=>{if(!token)return;try{const r=await fetch(API+"/api/v1/operational-alerts?limit=40",{headers:{Authorization:"Bearer "+token},cache:"no-store"});const d=await r.json();if(!r.ok)throw new Error(d.detail||"Unable to load alerts");setItems(d.items||[]);setError("")}catch(e){setError(e instanceof Error?e.message:"Unable to load alerts")}},[token]);
 useEffect(()=>{setToken(localStorage.getItem("ago_access_token")||"")},[]);
 useEffect(()=>{if(!token)return;void load();const id=window.setInterval(()=>void load(),15000);return()=>window.clearInterval(id)},[token,load]);
 async function markRead(item:Alert){const r=await fetch(API+"/api/v1/operational-alerts/"+item.id+"/read",{method:"PATCH",headers:{"Authorization":"Bearer "+token,"Content-Type":"application/json"},body:JSON.stringify({read:!item.read})});if(r.ok)setItems(old=>old.map(x=>x.id===item.id?{...x,read:!item.read}:x))}
 const unread=items.filter(x=>!x.read).length;
 return <div style={{position:"relative",display:"inline-flex",alignItems:"center"}}>
 <button aria-label={"Operational alerts, "+unread+" unread"} onClick={()=>setOpen(x=>!x)} style={{position:"relative",border:"1px solid #e1e7f0",background:"#fff",borderRadius:10,width:40,height:40,display:"grid",placeItems:"center",cursor:"pointer",color:"#26324a"}}><Bell size={18}/>{unread>0&&<span style={{position:"absolute",right:-4,top:-4,minWidth:17,height:17,borderRadius:99,background:"#d92d20",color:"#fff",fontSize:10,fontWeight:800,display:"grid",placeItems:"center",padding:"0 3px"}}>{unread>99?"99+":unread}</span>}</button>
 {open&&<div style={{position:"absolute",zIndex:1000,right:0,top:48,width:"min(390px, calc(100vw - 28px))",maxHeight:480,overflow:"auto",background:"#fff",border:"1px solid #e1e7f0",borderRadius:14,boxShadow:"0 14px 40px #18243b24",padding:12}}>
 <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"4px 4px 10px"}}><strong style={{color:"#17213a"}}>Operational alerts</strong><button onClick={()=>setOpen(false)} aria-label="Close alerts" style={{border:0,background:"transparent",cursor:"pointer"}}><X size={16}/></button></div>
 {error&&<p style={{fontSize:12,color:"#b42318"}}>{error}</p>}
 {items.length===0&&!error&&<p style={{fontSize:13,color:"#75839a",padding:10}}>No alerts yet. New bookings, orders and ticket updates will appear here.</p>}
 {items.map(item=><div key={item.id} style={{padding:10,borderTop:"1px solid #edf0f5",background:item.read?"#fff":"#f4f7ff",borderRadius:8,marginBottom:4}}>
 <div style={{display:"flex",gap:8,alignItems:"start"}}><div style={{flex:1}}><div style={{fontWeight:750,fontSize:13,color:"#17213a"}}>{item.title}</div><div style={{fontSize:12,color:"#526078",marginTop:4,whiteSpace:"pre-wrap"}}>{item.message}</div><div style={{fontSize:10,color:"#8994a8",marginTop:5}}>{new Date(item.created_at).toLocaleString()}</div></div><button title={item.read?"Mark unread":"Mark read"} onClick={()=>void markRead(item)} style={{border:0,background:"transparent",cursor:"pointer",color:"#5365d8"}}><Check size={16}/></button></div>
 </div>)}
 <button onClick={()=>void load()} style={{marginTop:8,width:"100%",padding:9,border:"1px solid #e1e7f0",borderRadius:8,background:"#fff",cursor:"pointer"}}>Refresh alerts</button>
 </div>}
 </div>
}
