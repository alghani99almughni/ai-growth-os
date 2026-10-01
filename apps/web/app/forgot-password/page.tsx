"use client";
import {useState} from "react";

const api=()=>process.env.NEXT_PUBLIC_API_URL||"https://ai-growth-os-api.onrender.com";

export default function ForgotPassword(){
 const [email,setEmail]=useState("");
 const [status,setStatus]=useState("");
 async function submit(e:any){
  e.preventDefault();setStatus("Sending reset instructions...");
  try{
   const r=await fetch(api()+"/api/v1/auth/password-reset/request",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email})});
   setStatus(r.ok?"If the account exists, reset instructions have been sent.":"Unable to process the request.");
  }catch{setStatus("Unable to connect to the account service.");}
 }
 return <main className="shell"><div className="card" style={{maxWidth:480,margin:"60px auto"}}>
  <p>AI GROWTH OS</p><h1>Forgot password?</h1><p>Enter your account email and we will send a secure reset link.</p>
  <form onSubmit={submit}><label>Email<input required type="email" value={email} onChange={e=>setEmail(e.target.value)} style={{display:"block",width:"100%",padding:12,margin:"6px 0 16px"}}/></label>
  <button type="submit" style={{padding:"12px 18px"}}>Send reset link</button></form>
  {status&&<p>{status}</p>}<p><a href="/login">Back to sign in</a></p>
 </div></main>
}