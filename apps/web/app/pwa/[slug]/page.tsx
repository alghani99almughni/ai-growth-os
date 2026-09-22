"use client";

import {useEffect} from "react";
import {useParams} from "next/navigation";

export default function TenantPwa(){
  const params=useParams<{slug:string}>();
  const slug=params?.slug||"";
  useEffect(()=>{
    if(!slug)return;
    const query=new URLSearchParams(window.location.search);
    query.set("business",slug);
    window.location.replace("/customer?"+query.toString());
  },[slug]);
  return <main className="shell"><section className="hero"><p>AI GROWTH OS</p><h1>Loading your customer experience…</h1></section></main>;
}
