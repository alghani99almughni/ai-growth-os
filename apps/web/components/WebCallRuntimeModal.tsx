"use client";

import {useEffect} from "react";

type Props={onClose:()=>void};

export default function WebCallRuntimeModal({onClose}:Props){
  useEffect(()=>{
    const handler=()=>onClose();
    window.addEventListener("webcall-runtime-close",handler);
    return()=>window.removeEventListener("webcall-runtime-close",handler);
  },[onClose]);

  return <div style={{position:"fixed",inset:0,zIndex:9999,background:"#030a16"}}>
    <iframe title="AI Growth OS Web Call Runtime" src="/call-runtime/index.html" style={{width:"100%",height:"100%",border:0}} allow="microphone; autoplay"/>
    <button type="button" onClick={onClose} aria-label="Close Web Call Runtime" style={{position:"fixed",right:18,top:14,zIndex:10000,width:42,height:42,borderRadius:999,border:"1px solid #ffffff33",background:"#07101dcc",color:"#fff",fontSize:24,cursor:"pointer"}}>×</button>
  </div>;
}
