"use client";
import {useEffect,useState} from "react";
const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
export default function BusinessBrain(){
 const [tenant,setTenant]=useState<any>(null),[instructions,setInstructions]=useState(""),[publishWebsite,setPublishWebsite]=useState(true),[data,setData]=useState<any>(null),[status,setStatus]=useState("");
 const token=()=>localStorage.getItem("ago_access_token")||"";
 const headers=()=>({Authorization:"Bearer "+token()});
 async function load(t:any){const r=await fetch(api()+"/api/v1/tenants/"+t.id+"/business-brain",{headers:headers()});if(r.ok){const x=await r.json();setData(x);setInstructions(x.instructions||"");setPublishWebsite(x.publish_website_to_agent!==false);}}
 useEffect(()=>{const raw=localStorage.getItem("ago_tenant");if(!raw){location.href="/login";return}const t=JSON.parse(raw);setTenant(t);load(t);},[]);
 async function save(){if(!tenant)return;const r=await fetch(api()+"/api/v1/tenants/"+tenant.id+"/business-brain",{method:"PUT",headers:{...headers(),"Content-Type":"application/json"},body:JSON.stringify({instructions,publish_website_to_agent:publishWebsite})});setStatus(r.ok?"Business Brain saved. Voice, chat and future channels will use the updated tenant rules.":"Could not save Business Brain.");if(r.ok)load(tenant);}
 return <main className="shell">
  <section className="hero"><p>AI GROWTH OS • TENANT CONTROL</p><h1>Business Brain</h1><p>Tell the agent how this business works. Tenant configuration is the source of truth for AI behavior.</p></section>
  <section className="card"><div style={{display:"flex",justifyContent:"space-between",gap:12,flexWrap:"wrap",alignItems:"center"}}><div><h2>🧠 Business instructions</h2><p>Write normal business instructions. No code or prompt engineering required.</p></div><a className="button" href="/dashboard">← Dashboard</a></div>
   <textarea value={instructions} onChange={e=>setInstructions(e.target.value)} placeholder={"Examples:\n\nConsultation costs ₹500.\nPremium wellness program costs ₹2,999.\nWe are open Monday to Saturday, 9 AM to 6 PM.\nAppointments are required for consultations.\nDo not promise same-day delivery."} style={{minHeight:280,width:"100%",marginTop:16}}/>
   <label className="card" style={{display:"block",marginTop:12}}><input type="checkbox" checked={publishWebsite} onChange={e=>setPublishWebsite(e.target.checked)}/> Allow approved public website content to be used by the agent</label>
   <button onClick={save}>Save Business Brain</button>{status&&<p aria-live="polite">{status}</p>}
  </section>
  <section className="grid">
   <article className="card"><h2>⚙️ Enabled capabilities</h2><p>The agent may use only capabilities enabled by this tenant.</p><div className="grid">{Object.entries(data?.features||{}).map(([k,v]:any)=><div className="card" key={k}><b>{k.replaceAll("_"," ")}</b><p>{v?"🟢 Enabled":"🔴 Disabled"}</p></div>)}</div></article>
   <article className="card"><h2>💰 Current pricing</h2><p>Services and products are read directly from tenant data.</p>{(data?.services||[]).map((x:any)=><p key={x.id}><b>{x.name}</b> — {x.price==null?"Price not configured":x.currency+" "+x.price}</p>)}{(data?.products||[]).map((x:any)=><p key={x.id}><b>{x.name}</b> — {x.price==null?"Price not configured":x.currency+" "+x.price}</p>)}{!data?.services?.length&&!data?.products?.length&&<p>No structured pricing configured yet. Add services/products or put approved pricing in Business Brain.</p>}</article>
  </section>
  <section className="card"><h2>🔒 How the agent follows this</h2><p><b>1.</b> Tenant capability settings decide what the agent is allowed to do.</p><p><b>2.</b> Tenant-approved instructions and website content provide business facts.</p><p><b>3.</b> Services, products and business hours provide live structured data.</p><p><b>4.</b> AI providers receive approved tenant context only; they are not the source of truth.</p><p><b>5.</b> Server-side workflow guards prevent disabled actions from being executed even if an AI provider requests them.</p></section>
 </main>
}