"use client";
import { FormEvent, useState } from "react";

export default function Onboarding() {
  const [form, setForm] = useState({name:"", email:"", password:"", business_name:"", slug:"", industry:"dental"});
  const [result, setResult] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    setResult("Creating your secure workspace...");
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const r = await fetch(base + "/api/v1/auth/register", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(form)
    });
    const data = await r.json();
    if (!r.ok) { setResult(data.detail || "Could not create account"); return; }
    localStorage.setItem("ago_access_token", data.access_token);
    localStorage.setItem("ago_user", JSON.stringify(data.user));
    localStorage.setItem("ago_tenant", JSON.stringify(data.tenant));
    setResult("Business created successfully. Your secure workspace is ready.");
    window.location.href = "/dashboard";
  }

  const inputStyle={display:"block",width:"100%",padding:12,margin:"6px 0 16px"};

  return <main className="shell"><div className="card" style={{maxWidth:620,margin:"40px auto"}}>
    <p>AI GROWTH OS</p><h1>Create your business workspace</h1>
    <p>One account creates your business, tenant and secure owner access.</p>
    <form onSubmit={submit}>
      <label>Your name<input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} style={inputStyle}/></label>
      <label>Email<input required type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} style={inputStyle}/></label>
      <label>Password<input required minLength={8} type="password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} style={inputStyle}/></label>
      <label>Business name<input required value={form.business_name} onChange={e=>setForm({...form,business_name:e.target.value})} style={inputStyle}/></label>
      <label>Business slug<input required pattern="[a-z0-9-]+" value={form.slug} onChange={e=>setForm({...form,slug:e.target.value.toLowerCase()})} style={inputStyle}/></label>
      <label>Industry<select value={form.industry} onChange={e=>setForm({...form,industry:e.target.value})} style={inputStyle}>
        <option value="dental">Dental</option><option value="restaurant">Restaurant</option><option value="hotel">Hotel</option><option value="salon">Salon</option><option value="gym">Gym</option><option value="real-estate">Real Estate</option>
      </select></label>
      <button type="submit" style={{padding:"12px 18px"}}>Create secure workspace</button>
    </form>{result&&<p>{result}</p>}
  </div></main>
}
