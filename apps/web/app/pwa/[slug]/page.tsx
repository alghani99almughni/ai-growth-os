"use client";

import {useEffect} from "react";

export default function TenantPwa({params}:{params:{slug:string}}){
  useEffect(()=>{
    const query=new URLSearchParams(window.location.search);
    query.set("business",params.slug);
    const target="/customer?"+query.toString();
    if(window.location.pathname!==target) window.location.replace(target);
  },[params.slug]);
  return <main className="shell"><section className="hero"><p>AI GROWTH OS</p><h1>Loading your customer experience…</h1></section></main>;
}
