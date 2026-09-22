"use client";
import {useEffect,useState} from "react";

const api=()=>process.env.NEXT_PUBLIC_API_URL||"https://ai-growth-os-api.onrender.com";

export default function ResetPassword(){
 const [token,setToken]=useState("");
 const [password,setPassword]=useState("");
 const [confirm,setConfirm]=useState("");
 const [show,setShow]=useState(false);
 const [status,setStatus]=useState("");
 useEffect(()=>{setToken(new URLSearchParams(window.location.search).get("token")||"")},[]);
 async function submit(e:any){
  e.preventDefault();
  if(password.length<8){setStatus("Password must be at least 8 characters.");return}
  if(password!==confirm){setStatus("Passwords do not match.");return}
  setStatus("Updating password...");
  try{
   const r=await fetch(api()+"/api/v1/auth/password-reset/confirm",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({token,password})});
   const x=await r.json().catch(()=>({}));
   if(!r.ok){setStatus(x?.detail||"Reset link is invalid or expired.");return}
   setStatus("Password updated. You can now sign in.");
  }catch{setStatus("Unable to connect to the account service.");}
 }
 return <main className="shell"><div className="card" style={{maxWidth:480,margin:"60px auto"}}>
  <p>AI GROWTH OS</p><h1>Create a new password</h1>
  {!token?<p>Missing reset token. Request a new reset link.</p>:<form onSubmit={submit}>
   <label>New password<input required minLength={8} type={show?"text":"password"} value={password} onChange={e=>setPassword(e.target.value)} style={{display:"block",width:"100%",padding:12,margin:"6px 0 16px"}}/></label>
   <label>Confirm password<input required minLength={8} type={show?"text":"password"} value={confirm} onChange={e=>setConfirm(e.target.value)} style={{display:"block",width:"100%",padding:12,margin:"6px 0 16px"}}/></label>
   <button type="button" onClick={()=>setShow(!show)}>{show?"Hide password":"Preview password"}</button>
   <button type="submit" style={{padding:"12px 18px",marginLeft:8}}>Update password</button>
  </form>}
  {status&&<p>{status}</p>}<p><a href="/login">Back to sign in</a></p>
 </div></main>
}