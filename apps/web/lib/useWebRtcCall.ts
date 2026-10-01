"use client";

import {useCallback,useEffect,useRef,useState} from "react";

const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";

function wsBase(){
  return api().replace(/^http:/,"ws:").replace(/^https:/,"wss:");
}

type Role="customer"|"staff";
type Status="idle"|"waiting"|"connecting"|"live"|"ended"|"rejected"|"error";

const ICE_SERVERS:RTCIceServer[]=[
  {urls:"stun:stun.l.google.com:19302"},
  {urls:"stun:stun1.l.google.com:19302"},
];

export function useWebRtcCall(roomId:string|undefined,role:Role,credential?:string){
  const [status,setStatus]=useState<Status>("idle");
  const [error,setError]=useState("");
  const [muted,setMuted]=useState(false);
  const audioRef=useRef<HTMLAudioElement|null>(null);
  const wsRef=useRef<WebSocket|null>(null);
  const pcRef=useRef<RTCPeerConnection|null>(null);
  const streamRef=useRef<MediaStream|null>(null);
  const closedRef=useRef(false);
  const pendingCandidates=useRef<RTCIceCandidateInit[]>([]);

  const cleanup=useCallback(()=>{
    closedRef.current=true;
    try{wsRef.current?.close();}catch{}
    try{pcRef.current?.close();}catch{}
    streamRef.current?.getTracks().forEach(t=>t.stop());
    wsRef.current=null;
    pcRef.current=null;
    streamRef.current=null;
  },[]);

  useEffect(()=>{
    if(!roomId||!credential||typeof window==="undefined")return;
    closedRef.current=false;
    setStatus("waiting");
    setError("");
    setMuted(false);

    const pc=new RTCPeerConnection({iceServers:ICE_SERVERS});
    pcRef.current=pc;

    const wsUrl=wsBase()+"/ws/calls/"+encodeURIComponent(roomId)+
      (role==="staff"?"?access_token=":"?room_token=")+encodeURIComponent(credential);
    const ws=new WebSocket(wsUrl);
    wsRef.current=ws;

    const send=(message:any)=>{
      if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify(message));
    };

    pc.onicecandidate=(event)=>{
      if(event.candidate)send({type:"signal",data:{candidate:event.candidate.toJSON()}});
    };

    pc.ontrack=(event)=>{
      const stream=event.streams[0];
      if(audioRef.current&&stream){
        audioRef.current.srcObject=stream;
        audioRef.current.play().catch(()=>{});
      }
    };

    pc.onconnectionstatechange=()=>{
      if(pc.connectionState==="connected")setStatus("live");
      else if(pc.connectionState==="failed"){
        setStatus("error");
        setError("Call connection failed. Please try again.");
      }else if(pc.connectionState==="disconnected")setStatus("connecting");
    };

    const micReady=navigator.mediaDevices?.getUserMedia({audio:true}).then(stream=>{
      if(closedRef.current){
        stream.getTracks().forEach(t=>t.stop());
        return;
      }
      streamRef.current=stream;
      stream.getTracks().forEach(track=>pc.addTrack(track,stream));
    }).catch(()=>{
      setStatus("error");
      setError("Microphone permission is required.");
      throw new Error("microphone");
    });

    ws.onopen=async()=>{
      send({type:"join",role});
      if(role==="customer"){
        setStatus("waiting");
      }
    };

    ws.onmessage=async(event)=>{
      if(closedRef.current)return;
      let message:any;
      try{message=JSON.parse(event.data);}catch{return}

      if(message.type==="ready"&&role==="customer"){
        await micReady;
        setStatus("connecting");
        const offer=await pc.createOffer();
        await pc.setLocalDescription(offer);
        send({type:"signal",data:{sdp:pc.localDescription?.toJSON()}});
        return;
      }

      if(message.type==="peer_joined"){
        setStatus("connecting");
        return;
      }

      if(message.type==="signal"){
        const {sdp,candidate}=message.data||{};
        if(sdp){
          await micReady;
          await pc.setRemoteDescription(sdp);
          if(sdp.type==="offer"&&role==="staff"){
            const answer=await pc.createAnswer();
            await pc.setLocalDescription(answer);
            send({type:"signal",data:{sdp:pc.localDescription?.toJSON()}});
          }
          if(pendingCandidates.current.length){
            for(const item of pendingCandidates.current){
              await pc.addIceCandidate(item).catch(()=>{});
            }
            pendingCandidates.current=[];
          }
        }else if(candidate){
          if(pc.remoteDescription)await pc.addIceCandidate(candidate).catch(()=>{});
          else pendingCandidates.current.push(candidate);
        }
        return;
      }

      if(message.type==="ended"){
        setStatus("ended");
        return;
      }

      if(message.type==="rejected"){
        setStatus("rejected");
        setError(message.reason==="seat_taken"
          ?"Another team member has already answered this call."
          :"Call authorization was rejected.");
        return;
      }

      if(message.type==="error"){
        setStatus("error");
        setError(message.message||"Call signaling error.");
      }
    };

    ws.onerror=()=>{
      if(!closedRef.current){
        setStatus("error");
        setError("Unable to connect the call service.");
      }
    };

    ws.onclose=()=>{
      if(!closedRef.current&&status!=="ended"&&status!=="rejected"){
        setStatus((current)=>current==="live"?"ended":current);
      }
    };

    return cleanup;
  },[roomId,role,credential,cleanup]);

  const hangup=useCallback(()=>{
    try{
      if(wsRef.current?.readyState===WebSocket.OPEN)wsRef.current.send(JSON.stringify({type:"hangup"}));
    }catch{}
    setStatus("ended");
    cleanup();
  },[cleanup]);

  const toggleMute=useCallback(()=>{
    const next=!muted;
    streamRef.current?.getAudioTracks().forEach(track=>{track.enabled=!next;});
    setMuted(next);
  },[muted]);

  return {status,error,muted,audioRef,hangup,toggleMute};
}
