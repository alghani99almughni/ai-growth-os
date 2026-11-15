"use client";
import { FormEvent, useState } from "react";

export default function LoginPage() {
  const [email,setEmail]=useState("");
  const [password,setPassword]=useState("");
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  async function submit(e:FormEvent) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const response=await fetch((process.env.NEXT_PUBLIC_API_URL || "")+"/api/v1/auth/login",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({email,password}),cache:"no-store"
      });
      const data=await response.json().catch(()=>({}));
      if(!response.ok) throw new Error(data.detail || "Sign in failed");
      localStorage.setItem("ago_access_token",data.access_token);
      localStorage.setItem("ago_user",JSON.stringify(data.user));
      localStorage.setItem("ago_tenant",JSON.stringify(data.tenant));
      const isPlatform=["platform_admin","super_admin"].includes(data.user?.role);
      window.location.assign(isPlatform?"/platform/ai-voice":"/dashboard/ai-voice");
    } catch(err:any) { setError(err.message || "Unable to sign in"); }
    finally { setBusy(false); }
  }
  const field:React.CSSProperties={width:"100%",padding:"13px 14px",border:"1px solid #cbd5e1",borderRadius:10,background:"#fff",color:"#0f172a",fontSize:15};
  return <main style={{minHeight:"100vh",display:"grid",placeItems:"center",padding:24,background:"linear-gradient(145deg,#071827,#102f45)",fontFamily:"Arial,sans-serif"}}>
    <section style={{width:"100%",maxWidth:440,background:"#fff",borderRadius:20,padding:32,boxShadow:"0 24px 80px #0005",color:"#0f172a"}}>
      <a href="/" style={{fontSize:12,fontWeight:800,letterSpacing:2,color:"#0d9488",textDecoration:"none"}}>AI VOICE</a>
      <h1 style={{fontSize:30,fontWeight:800,margin:"16px 0 8px"}}>Welcome back</h1>
      <p style={{fontSize:14,color:"#64748b",marginBottom:24}}>Sign in to your business or platform workspace.</p>
      <form onSubmit={submit} style={{display:"grid",gap:14}}>
        <label style={{fontSize:13,fontWeight:700}}>Email<input required type="email" autoComplete="username" value={email} onChange={e=>setEmail(e.target.value)} style={{...field,display:"block",marginTop:7}}/></label>
        <label style={{fontSize:13,fontWeight:700}}>Password<input required type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} style={{...field,display:"block",marginTop:7}}/></label>
        {error&&<p role="alert" style={{padding:11,borderRadius:9,background:"#fff1f2",color:"#be123c",fontSize:13}}>{error}</p>}
        <button disabled={busy} type="submit" style={{border:0,borderRadius:10,padding:14,background:"#0f766e",color:"#fff",fontWeight:800,fontSize:14,cursor:"pointer",opacity:busy?.65:1}}>{busy?"Signing in…":"Sign in securely"}</button>
      </form>
      <p style={{fontSize:12,color:"#64748b",marginTop:20,lineHeight:1.6}}>New business accounts are provisioned by the AI Voice platform administrator. Contact the platform team if you need access.</p>
    </section>
  </main>;
}
