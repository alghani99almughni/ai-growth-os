"use client";
import {useEffect,useState} from "react";

const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
const keys=["facebook","instagram","meta_ads","youtube","google_business"];

export default function SocialStudio(){
  const [tenant,setTenant]=useState<any>(null),[health,setHealth]=useState<any>({}),[message,setMessage]=useState("");
  const [fb,setFb]=useState({message:"",link:""});
  const [ig,setIg]=useState({image_url:"",caption:""});
  const [gb,setGb]=useState({location_name:"",summary:"",topic_type:"STANDARD",action_type:"LEARN_MORE",action_url:"",image_url:""});
  const [yt,setYt]=useState({title:"",description:"",privacy_status:"private",category_id:"22",video:null as File|null});
  const [ads,setAds]=useState<any[]>([]);
  const token=()=>localStorage.getItem("ago_access_token")||"";
  const headers=()=>({Authorization:"Bearer "+token()});

  async function refresh(){
    if(!tenant)return;
    const result:any={};
    await Promise.all(keys.map(async k=>{
      const r=await fetch(api()+"/api/v1/tenants/"+tenant.id+"/social/"+k+"/health",{headers:headers()});
      result[k]=r.ok?await r.json():{connected:false};
    }));
    setHealth(result);
  }
  useEffect(()=>{const raw=localStorage.getItem("ago_tenant");if(!raw){location.href="/login";return}setTenant(JSON.parse(raw))},[]);
  useEffect(()=>{if(tenant)refresh()},[tenant]);

  async function postForm(path:string, form:FormData){
    const r=await fetch(api()+path,{method:"POST",headers:headers(),body:form});
    const x=await r.json();
    setMessage(r.ok?"Published successfully":(x.detail||"Provider request failed"));
    return r.ok;
  }
  async function publishFacebook(){
    const f=new FormData();f.append("message",fb.message);if(fb.link)f.append("link",fb.link);
    await postForm("/api/v1/tenants/"+tenant.id+"/social/facebook/publish",f);
  }
  async function publishInstagram(){
    const f=new FormData();f.append("image_url",ig.image_url);f.append("caption",ig.caption);
    await postForm("/api/v1/tenants/"+tenant.id+"/social/instagram/publish",f);
  }
  async function publishGoogle(){
    const f=new FormData();Object.entries(gb).forEach(([k,v])=>{if(v)f.append(k,String(v))});
    await postForm("/api/v1/tenants/"+tenant.id+"/social/google_business/post",f);
  }
  async function uploadYoutube(){
    if(!yt.video)return;
    const f=new FormData();f.append("title",yt.title);f.append("description",yt.description);f.append("privacy_status",yt.privacy_status);f.append("category_id",yt.category_id);f.append("video",yt.video);
    await postForm("/api/v1/tenants/"+tenant.id+"/social/youtube/upload",f);
  }
  async function loadAds(){
    const from=prompt("From date YYYY-MM-DD",new Date(Date.now()-7*86400000).toISOString().slice(0,10));if(!from)return;
    const to=prompt("To date YYYY-MM-DD",new Date().toISOString().slice(0,10));if(!to)return;
    const r=await fetch(api()+"/api/v1/tenants/"+tenant.id+"/social/meta_ads/insights?date_from="+encodeURIComponent(from)+"&date_to="+encodeURIComponent(to),{headers:headers()});
    const x=await r.json();if(r.ok)setAds(x.items||[]);else setMessage(x.detail||"Unable to load ads insights");
  }
  if(!tenant)return <main className="shell"><section className="card"><h1>Loading Social Studio…</h1></section></main>;
  return <main className="shell">
    <section className="hero"><p>AI GROWTH OS • SOCIAL STUDIO</p><h1>Publish & measure</h1><p>One tenant-scoped workspace for connected Facebook, Instagram, Meta Ads, YouTube and Google Business accounts.</p></section>
    {message&&<section className="card"><strong>{message}</strong></section>}
    <section className="grid">{keys.map(k=><article className="card" key={k}><h3>{k.replace("_"," ").toUpperCase()}</h3><p>{health[k]?.connected?"● Connected":"○ Not connected"}</p>{health[k]?.account_name&&<small>{health[k].account_name}</small>}</article>)}</section>
    <section className="grid">
      <article className="card"><h2>Facebook</h2><label>Post message<textarea value={fb.message} onChange={e=>setFb({...fb,message:e.target.value})}/></label><label>Link (optional)<input value={fb.link} onChange={e=>setFb({...fb,link:e.target.value})}/></label><button onClick={publishFacebook}>Publish to Facebook</button></article>
      <article className="card"><h2>Instagram</h2><label>Public image URL<input value={ig.image_url} onChange={e=>setIg({...ig,image_url:e.target.value})}/></label><label>Caption<textarea value={ig.caption} onChange={e=>setIg({...ig,caption:e.target.value})}/></label><button onClick={publishInstagram}>Publish to Instagram</button></article>
      <article className="card"><h2>Google Business</h2><label>Location resource name<input value={gb.location_name} onChange={e=>setGb({...gb,location_name:e.target.value})} placeholder="accounts/123/locations/456"/></label><label>Summary<textarea value={gb.summary} onChange={e=>setGb({...gb,summary:e.target.value})}/></label><label>Action URL<input value={gb.action_url} onChange={e=>setGb({...gb,action_url:e.target.value})}/></label><button onClick={publishGoogle}>Publish local post</button></article>
      <article className="card"><h2>YouTube</h2><label>Title<input value={yt.title} onChange={e=>setYt({...yt,title:e.target.value})}/></label><label>Description<textarea value={yt.description} onChange={e=>setYt({...yt,description:e.target.value})}/></label><label>Privacy<select value={yt.privacy_status} onChange={e=>setYt({...yt,privacy_status:e.target.value})}><option>private</option><option>unlisted</option><option>public</option></select></label><label>Video<input type="file" accept="video/*" onChange={e=>setYt({...yt,video:e.target.files?.[0]||null})}/></label><button onClick={uploadYoutube}>Upload to YouTube</button></article>
    </section>
    <section className="card"><div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><div><h2>Meta Ads insights</h2><p>Campaign-level delivery and spend metrics for the selected date range.</p></div><button onClick={loadAds}>Load insights</button></div>{ads.length>0?<div className="grid">{ads.map((x:any,i:number)=><article className="card" key={i}><h3>{x.campaign_name||"Campaign"}</h3><p>Spend: {x.spend||"0"} • Impressions: {x.impressions||"0"} • Clicks: {x.clicks||"0"}</p><p>CTR: {x.ctr||"0"} • CPC: {x.cpc||"0"} • CPM: {x.cpm||"0"}</p></article>)}</div>:<p>No insights loaded.</p>}</section>
    <button onClick={()=>location.href="/dashboard"}>← Back to Business Dashboard</button>
  </main>;
}
