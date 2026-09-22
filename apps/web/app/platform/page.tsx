"use client";
import {useEffect,useState} from "react";
const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
export default function Platform(){
 const [items,setItems]=useState<any[]>([]),[status,setStatus]=useState(""),[form,setForm]=useState<any>({business_name:"",slug:"",industry:"wellness",owner_name:"",owner_email:"",owner_password:"",phone:"",whatsapp_number:"",address:""});
 const token=()=>localStorage.getItem("ago_access_token")||"";
 async function load(){const r=await fetch(api()+"/api/v1/platform/tenants",{headers:{Authorization:"Bearer "+token()}});if(r.status===403){location.href="/dashboard";return}const x=await r.json();if(r.ok)setItems(x.items||[]);else setStatus(x.detail||"Unable to load tenants");}
 useEffect(()=>{load()},[]);
 async function provision(e:any){e.preventDefault();setStatus("Provisioning business...");const r=await fetch(api()+"/api/v1/platform/tenants/provision",{method:"POST",headers:{Authorization:"Bearer "+token(),"Content-Type":"application/json"},body:JSON.stringify(form)});const x=await r.json();if(!r.ok){setStatus(x.detail||"Provisioning failed");return}setStatus("Tenant activated: "+x.tenant.name+" • owner login "+x.owner.email);setForm({business_name:"",slug:"",industry:"wellness",owner_name:"",owner_email:"",owner_password:"",phone:"",whatsapp_number:"",address:""});load();}
 return <main className="shell"><section className="hero"><p>AI GROWTH OS • PLATFORM SUPER ADMIN</p><h1>Business Provisioning Center</h1><p>Create and activate a complete tenant in one flow.</p></section>
 <section className="card"><h2>+ Provision New Tenant</h2><form onSubmit={provision} className="grid">
 {["business_name","slug","owner_name","owner_email","owner_password","phone","whatsapp_number","address"].map(k=><label key={k}>{k.replaceAll("_"," ")}<input required={["business_name","slug","owner_name","owner_email","owner_password"].includes(k)} type={k==="owner_password"?"password":k==="owner_email"?"email":"text"} value={form[k]} onChange={e=>setForm({...form,[k]:e.target.value})}/></label>)}
 <label>Industry<select value={form.industry} onChange={e=>setForm({...form,industry:e.target.value})}>{["wellness","health","dental","restaurant","hotel","salon","gym","real-estate","education"].map(x=><option key={x}>{x}</option>)}</select></label>
 <button type="submit">Create & Activate Tenant</button></form><p>{status}</p></section>
 <section className="card"><h2>Tenants</h2>{items.map(t=><article className="card" key={t.id}><strong>{t.name}</strong><p>{t.industry} • {t.slug} • {t.status}</p></article>)}{!items.length&&<p>No tenants yet.</p>}</section></main>;
}