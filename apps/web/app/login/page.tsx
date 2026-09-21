"use client";
import { FormEvent, useState } from "react";

export default function Login() {
  const [form,setForm]=useState({email:"",password:""});
  const [error,setError]=useState("");
  async function submit(e:FormEvent){
    e.preventDefault(); setError("");
    const base=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
    const r=await fetch(base+"/api/v1/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(form)});
    const data=await r.json();
    if(!r.ok){setError(data.detail||"Login failed");return;}
    localStorage.setItem("ago_access_token",data.access_token);
    localStorage.setItem("ago_user",JSON.stringify(data.user));
    localStorage.setItem("ago_tenant",JSON.stringify(data.tenant));
    window.location.href="/dashboard";
  }
  return <main className="shell"><div className="card" style={{maxWidth:480,margin:"60px auto"}}>
    <p>AI GROWTH OS</p><h1>Sign in</h1><p>Access your business workspace.</p>
    <form onSubmit={submit}>
      <label>Email<input required type="email" value={form.email} onChange={e=>setForm({...form,email:e.target.value})} style={{display:"block",width:"100%",padding:12,margin:"6px 0 16px"}}/></label>
      <label>Password<input required type="password" value={form.password} onChange={e=>setForm({...form,password:e.target.value})} style={{display:"block",width:"100%",padding:12,margin:"6px 0 16px"}}/></label>
      <button type="submit" style={{padding:"12px 18px"}}>Sign in</button>
    </form>{error&&<p>{error}</p>}
  </div></main>
}