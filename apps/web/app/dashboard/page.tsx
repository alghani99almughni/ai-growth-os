"use client";
import { useEffect, useState } from "react";

export default function Dashboard(){
  const [user,setUser]=useState<any>(null);
  useEffect(()=>{const raw=localStorage.getItem("ago_user"); if(!raw){window.location.href="/login";return;} setUser(JSON.parse(raw));},[]);
  if(!user) return <main className="shell"><div className="card">Loading workspace...</div></main>;
  return <main className="shell"><div className="card" style={{maxWidth:1000,margin:"40px auto"}}>
    <p>AI GROWTH OS</p><h1>Business Dashboard</h1>
    <p>Welcome, {user.name}. Your tenant: <strong>{user.tenant_id}</strong></p>
    <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:12,marginTop:24}}>
      <div className="card"><strong>Customers</strong><p>CRM foundation</p></div>
      <div className="card"><strong>Leads</strong><p>Lead pipeline</p></div>
      <div className="card"><strong>AI Brain</strong><p>Coming next</p></div>
      <div className="card"><strong>Calls</strong><p>Voice engine</p></div>
    </div>
    <button onClick={()=>{localStorage.clear();window.location.href="/login"}} style={{marginTop:24,padding:"10px 16px"}}>Sign out</button>
  </div></main>
}