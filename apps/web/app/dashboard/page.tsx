"use client";
import {useEffect,useState} from "react";
const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
export default function Dashboard(){
 const [user,setUser]=useState<any>(); const [tenant,setTenant]=useState<any>(); const [services,setServices]=useState<any[]>([]); const [products,setProducts]=useState<any[]>([]); const [tab,setTab]=useState("overview");
 useEffect(()=>{const u=localStorage.getItem("ago_user"),t=localStorage.getItem("ago_tenant");if(!u){location.href="/login";return}setUser(JSON.parse(u));setTenant(t?JSON.parse(t):null)},[]);
 async function load(){if(!tenant)return;const h={Authorization:"Bearer "+localStorage.getItem("ago_access_token")};const s=await fetch(api()+"/api/v1/tenants/"+tenant.id+"/services",{headers:h});const p=await fetch(api()+"/api/v1/tenants/"+tenant.id+"/products",{headers:h});setServices((await s.json()).items||[]);setProducts((await p.json()).items||[])}
 useEffect(()=>{load()},[tenant]);
 async function add(kind:string){const name=prompt("New "+kind+" name");if(!name||!tenant)return;const h={"Content-Type":"application/json",Authorization:"Bearer "+localStorage.getItem("ago_access_token")};await fetch(api()+"/api/v1/tenants/"+tenant.id+"/"+kind+"s",{method:"POST",headers:h,body:JSON.stringify({name,price:0,currency:"INR",is_active:true})});load()}
 if(!user)return <main className="shell"><div className="card">Loading workspace...</div></main>;
 return <main className="shell"><div className="hero"><p>AI GROWTH OS</p><h1>{tenant?.name||"Business Dashboard"}</h1><p>AI customer engagement, CRM, calls, QR and growth in one workspace.</p></div>
 <nav className="tabs">{["overview","catalog","customers","brain","calls"].map(x=><button key={x} onClick={()=>setTab(x)}>{x}</button>)}<button onClick={()=>{localStorage.clear();location.href="/login"}}>Sign out</button></nav>
 {tab==="overview"&&<section className="grid"><div className="card"><b>Customer CRM</b><p>Customers, leads and relationship history.</p></div><div className="card"><b>AI Brain</b><p>Approved business data, FAQs and AI answers.</p></div><div className="card"><b>Voice</b><p>WebRTC call records and AI handoff architecture.</p></div><div className="card"><b>Growth</b><p>QR entry points, campaigns and loyalty foundation.</p></div></section>}
 {tab==="catalog"&&<section className="grid"><div className="card"><h2>Services</h2><button onClick={()=>add("service")}>Add service</button>{services.map(x=><p key={x.id}>{x.name} · {x.price??"—"} {x.currency}</p>)}</div><div className="card"><h2>Products</h2><button onClick={()=>add("product")}>Add product</button>{products.map(x=><p key={x.id}>{x.name} · {x.price??"—"} {x.currency}</p>)}</div></section>}
 {tab==="customers"&&<div className="card"><h2>Customers & Leads</h2><p>Tenant-scoped CRM APIs are live. Customer PWA interactions can create identified customers and leads.</p></div>}
 {tab==="brain"&&<div className="card"><h2>Business Brain</h2><p>Use the authenticated knowledge API to add approved FAQs, policies and business facts. AI answers are constrained to approved context.</p></div>}
 {tab==="calls"&&<div className="card"><h2>AI-first calling</h2><p>Call records and lifecycle states are ready for WebRTC signaling, STT/TTS adapters and department routing.</p></div>}
 </main>
}