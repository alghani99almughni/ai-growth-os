"use client";

import {useEffect,useState} from "react";
import {useParams} from "next/navigation";

const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";

export default function TenantPwa(){
  const params=useParams<{slug:string}>();
  const slug=params?.slug||"";
  const [business,setBusiness]=useState<any>(null);
  const [website,setWebsite]=useState<any>(null);
  const [installPrompt,setInstallPrompt]=useState<any>(null);
  const [installed,setInstalled]=useState(false);

  useEffect(()=>{
    if(!slug)return;
    if(slug!=="ss-nutritions"){
      const q=new URLSearchParams(window.location.search); q.set("business",slug);
      window.location.replace("/customer?"+q.toString()); return;
    }
    Promise.all([
      fetch(api()+"/api/v1/public/business/"+encodeURIComponent(slug)).then(r=>r.ok?r.json():null),
      fetch(api()+"/api/v1/public/business/"+encodeURIComponent(slug)+"/website").then(r=>r.ok?r.json():null)
    ]).then(([b,w])=>{setBusiness(b);setWebsite(w)}).catch(()=>{});
    const handler=(e:any)=>{e.preventDefault();setInstallPrompt(e)};
    window.addEventListener("beforeinstallprompt",handler);
    setInstalled(window.matchMedia?.("(display-mode: standalone)")?.matches||false);
    return()=>window.removeEventListener("beforeinstallprompt",handler);
  },[slug]);

  const content=website?.content||{};
  const phone=String(content.whatsapp_number||business?.whatsapp_number||"").replace(/\D/g,"");
  const wa="https://wa.me/"+phone+"?text="+encodeURIComponent("Hi SS Nutritions, I would like to know more about your wellness programs.");
  const customer="/customer?business=ss-nutritions";

  if(slug!=="ss-nutritions") return <main className="shell"><section className="hero"><p>AI GROWTH OS</p><h1>Loading your customer experience…</h1></section></main>;

  return <main className="ss-pwa">
    <div className="ss-pwa-top">
      <div className="ss-pwa-brand"><span>SS</span><div><strong>SS Nutritions</strong><small>Healthy choices · Moinabad</small></div></div>
      {!installed&&installPrompt&&<button className="ss-pwa-install" onClick={async()=>{await installPrompt.prompt();setInstallPrompt(null)}}>Install app</button>}
    </div>

    <section className="ss-pwa-hero">
      <div className="ss-pwa-mark">🌿</div>
      <p className="ss-eyebrow">YOUR WELLNESS SPACE</p>
      <h1>Feel better.<br/><em>Live consciously.</em></h1>
      <p>Practical wellness support with an organic-focused approach to healthier everyday choices.</p>
      <div className="ss-pwa-actions">
        <a className="ss-pwa-primary" href={customer}>Open wellness space <span>↗</span></a>
        <a className="ss-pwa-secondary" href={wa} target="_blank" rel="noreferrer">WhatsApp us</a>
      </div>
    </section>

    <section className="ss-pwa-call">
      <div><span className="ss-pwa-live-dot"/> <strong>Talk to SS Nutritions</strong><p>Have a question? Start a private AI-assisted call.</p></div>
      <a href="/ss-nutritions#call" onClick={(e)=>{e.preventDefault();window.location.href="/ss-nutritions#call"}}>Call us</a>
    </section>

    <section className="ss-pwa-cards">
      <article><span>🥗</span><strong>Nutrition guidance</strong><p>Practical everyday food and wellness guidance.</p></article>
      <article><span>🌱</span><strong>Organic-focused living</strong><p>Explore thoughtful natural choices for your routine.</p></article>
      <article><span>🧘</span><strong>Healthy habits</strong><p>Small consistent actions that fit real life.</p></article>
    </section>

    <section className="ss-pwa-location">
      <span>📍</span><div><strong>SS Nutritions</strong><p>Moinabad, Rangareddy District<br/>Telangana · 501504</p></div>
    </section>

    <nav className="ss-pwa-nav">
      <a href="/ss-nutritions">Website</a>
      <a href={customer}>My space</a>
      <a href={wa} target="_blank" rel="noreferrer">WhatsApp</a>
    </nav>
  </main>;
}
