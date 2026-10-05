"use client";

import {useEffect} from "react";

type Props={
  onClose:()=>void;
  slug?:string;
  businessName?:string;
  existingCustomerId?:string;
  agentGender?:"male"|"female";
  onCustomerIdentified?:(customerId:string)=>void;
};

export default function WebCallRuntimeModal({
  onClose,
  slug="ss-nutritions",
  businessName="SS Nutritions",
  existingCustomerId,
}:Props){
  useEffect(()=>{
    const close=()=>onClose();
    window.addEventListener("webcall-runtime-close",close);
    return()=>window.removeEventListener("webcall-runtime-close",close);
  },[onClose]);

  const params = new URLSearchParams();
  params.set("slug", slug);
  params.set("business", businessName);
  if (existingCustomerId) params.set("customer", existingCustomerId);

  return (
    <div
      style={{position:"fixed",inset:0,zIndex:9999,background:"rgba(3,10,22,.72)",backdropFilter:"blur(12px)"}}
      role="dialog"
      aria-modal="true"
      aria-label={`AI call with ${businessName}`}
    >
      <iframe
        title="AI Growth OS Web Call Runtime"
        src={`/call-runtime/index.html?${params.toString()}`}
        style={{width:"100%",height:"100%",border:0,display:"block"}}
        allow="microphone; autoplay"
      />
      <button
        type="button"
        onClick={onClose}
        aria-label="Close call runtime"
        style={{position:"fixed",top:16,right:16,zIndex:10000,width:42,height:42,border:0,borderRadius:999,background:"rgba(0,0,0,.55)",color:"#fff",fontSize:28,lineHeight:1,cursor:"pointer"}}
      >×</button>
    </div>
  );
}
