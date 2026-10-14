"use client";
import {useEffect,useMemo,useState} from "react";
import VoiceCallModal from "../../components/VoiceCallModal";

const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
type Item={id:string;category_id?:string;name:string;description?:string;price:number;currency?:string};
type Cart=Record<string,number>;

const gameNames=["dino","snake","brick","flappy","tap","2048"];
const gameLabels:Record<string,string>={dino:"🦖 Dino Run",snake:"🐍 Snake",brick:"🧱 Brick Breaker",flappy:"🐦 Flappy",tap:"🎯 Tap Target","2048":"🔢 2048"};

export default function Customer(){
 const [slug,setSlug]=useState(""),[business,setBusiness]=useState<any>(null),[context,setContext]=useState(""),[customerId,setCustomerId]=useState(""),[cart,setCart]=useState<Cart>({}),[order,setOrder]=useState<any>(null),[menuOpen,setMenuOpen]=useState(false),[game,setGame]=useState<string|null>(null),[gameScore,setGameScore]=useState(0),[waiter,setWaiter]=useState<any>(null),[feedback,setFeedback]=useState(0),[comment,setComment]=useState(""),[feedbackSent,setFeedbackSent]=useState(false),[status,setStatus]=useState(""),[active,setActive]=useState("home"),[gamePoints,setGamePoints]=useState(0),[gameData,setGameData]=useState<any>({bricks:Array(12).fill(true),target:0,moves:0});
 const [customerName,setCustomerName]=useState("");
 const [callOpen,setCallOpen]=useState(false);
 const [storedCustomerId,setStoredCustomerId]=useState<string>("");
 const [callInstance,setCallInstance]=useState(0);

 useEffect(()=>{
  const p=new URLSearchParams(location.search);
  const directSlug=p.get("business")||"";
  const storedSlug=typeof window!=="undefined"?localStorage.getItem("cust:last-business")||"":"";
  setContext(p.get("context")||"");
  setCustomerId(p.get("customer")||"");
  const qr=p.get("qr")||"";

  const slugToUse=directSlug||storedSlug;
  if(slugToUse){
   if(directSlug) try{localStorage.setItem("cust:last-business",directSlug);}catch{}
   setSlug(slugToUse);
   try{
    const existing=typeof window!=="undefined"?localStorage.getItem(`cust:${slugToUse}:id`)||"":"";
    if(existing) setStoredCustomerId(existing);
   }catch{}
   try{
    const link=document.createElement("link");
    link.rel="manifest";
    link.href=`/customer/${encodeURIComponent(slugToUse)}/manifest.webmanifest`;
    document.head.appendChild(link);
   }catch{}
   return;
  }

  if(qr){
   fetch(api()+"/api/v1/public/qr/"+encodeURIComponent(qr)).then(r=>r.ok?r.json():null).then(d=>{
    if(d?.slug){
     setSlug(d.slug);
     if(d.kind==="table")setContext("Table QR");
     try{localStorage.setItem("cust:last-business",d.slug);}catch{}
     try{
      const existing=typeof window!=="undefined"?localStorage.getItem(`cust:${d.slug}:id`)||"":"";
      if(existing) setStoredCustomerId(existing);
     }catch{}
     try{
      const link=document.createElement("link");
      link.rel="manifest";
      link.href=`/customer/${encodeURIComponent(d.slug)}/manifest.webmanifest`;
      document.head.appendChild(link);
     }catch{}
    }else setStatus(d?.detail||"QR not found");
   }).catch(()=>setStatus("Unable to load this QR experience"));
  }else setStatus("Business QR or business link is required.");
 },[]);

 useEffect(()=>{if(!slug)return;fetch(api()+"/api/v1/public/business/"+encodeURIComponent(slug)).then(r=>r.json()).then(d=>{if(d.id)setBusiness(d);else setStatus(d.detail||"Business not found")})},[slug]);

 useEffect(()=>{if(!order||!business)return;const id=window.setInterval(()=>fetch(api()+"/api/v1/public/business/"+business.slug+"/orders/"+order.id).then(r=>r.json()).then(setOrder).catch(()=>{}),10000);return()=>clearInterval(id)},[order?.id,business?.slug]);

 useEffect(()=>{
  if(!business||!context)return;
  const base=api().replace(/^http/,"ws");
  const ws=new WebSocket(base+"/ws/public/business/"+encodeURIComponent(business.slug)+"/events?context_token="+encodeURIComponent(context));
  ws.onmessage=(e)=>{
   try{
    const event=JSON.parse(e.data);
    if(event.type==="order.created"||event.type==="order.updated"){
      const id=event.data?.order_id;
      if(!order||order.id===id){
       setOrder((current:any)=>current?{...current,status:event.data.status,total:event.data.total,payment_status:event.data.payment_status,bill:event.data.bill||current.bill}:current);
      }
      setStatus(event.type==="order.created"?"Order received":"Order status updated");
    }
    if(event.type==="service_request.created"||event.type==="service_request.updated"){
      setWaiter((current:any)=>({...current,...event.data,id:event.data.request_id,status:event.data.status}));
      setStatus("Service request updated");
    }
   }catch{}
  };
  return()=>ws.close();
 },[business?.slug,context,order?.id]);

 const items:Item[]=business?.menu?.items||[];
 const cats=business?.menu?.categories||[];
 const services:any[] = business?.services || [];
 const feature:any = business?.features || {};
 const categoryLabel = business?.industry_category || business?.industry || "Local business";
 const businessTypeLabel = business?.business_type || "";
 const profileText = (String(categoryLabel)+" "+String(businessTypeLabel)+" "+String(business?.industry||"")).toLowerCase();
 const isHospitality = ["hospitality","restaurant","cafe","café","hotel","eatery","eateries","bakery","food service","fine dining"].some(x=>profileText.includes(x));
 const showTableTools = isHospitality && !!feature.call_waiter;
 const showMenu = isHospitality && !!feature.digital_menu;
 const showGames = !!feature.games && (isHospitality || profileText.includes("fitness") || profileText.includes("gym"));
 const cartItems=useMemo(()=>items.filter(x=>cart[x.id]).map(x=>({...x,quantity:cart[x.id]})),[items,cart]);
 const total=cartItems.reduce((s,x)=>s+x.price*x.quantity,0);

 function add(id:string){setCart(c=>({...c,[id]:(c[id]||0)+1}))}
 function remove(id:string){setCart(c=>{const n={...c};n[id]=(n[id]||0)-1;if(n[id]<=0)delete n[id];return n})}

 async function placeOrder(){if(!business||!cartItems.length)return;setStatus("Placing order…");const r=await fetch(api()+"/api/v1/public/business/"+business.slug+"/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:cartItems.map(x=>({menu_item_id:x.id,quantity:x.quantity})),context_token:context||undefined,customer_id:customerId||undefined})});const d=await r.json();if(!r.ok){setStatus(d.detail||"Unable to place order");return}setOrder(d);setCart({});setActive("home");setStatus("Order placed successfully");}

 async function startTeamCall(){
  if(!business)return <main className="shell" style={{minHeight:"100vh",padding:"clamp(16px,4vw,44px)",background:"linear-gradient(145deg,#eef4ff 0%,#f8f5ff 48%,#effcf7 100%)"}}><section className="hero" style={{background:"linear-gradient(120deg,#172554,#4338ca 60%,#0f766e)",minHeight:280,display:"flex",flexDirection:"column",justifyContent:"center"}}><p style={{letterSpacing:".16em",fontWeight:800,fontSize:11}}>YOUR NEXT GREAT EXPERIENCE</p><h1>{slug||"Welcome"}</h1><p>{status||"Loading your business website…"}</p><div style={{display:"flex",gap:8,marginTop:24,alignItems:"center"}}><span style={{background:"rgba(255,255,255,.16)",padding:"8px 12px",borderRadius:999,fontSize:12}}>Personalised for you</span><span style={{fontSize:12,opacity:.8}}>One place. Everything you need.</span></div></section><div style={{padding:16,color:"#65718b",fontSize:12}}>Loading your business experience securely…</div></main>;

 const delivered=order&&["served","completed"].includes(order.status);
 return <main className="shell" style={{maxWidth:1240,padding:"clamp(14px,3vw,34px)",background:"linear-gradient(180deg,#f1f5ff 0%,#fafbff 360px,#f7f9fc 100%)",minHeight:"100vh"}}>
  <header style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:14,marginBottom:18,flexWrap:"wrap"}}>
   <div style={{display:"flex",alignItems:"center",gap:10}}><div style={{width:42,height:42,borderRadius:14,display:"grid",placeItems:"center",color:"#fff",fontSize:20,fontWeight:800,background:"linear-gradient(135deg,#6366f1,#0d9488)",boxShadow:"0 8px 24px #6366f133"}}>{String(business.name||"B").trim().charAt(0).toUpperCase()}</div><div><div style={{fontWeight:800,fontSize:15,color:"#18213b"}}>{business.name}</div><div style={{fontSize:11,color:"#74809b"}}>{categoryLabel}{businessTypeLabel?" · "+businessTypeLabel:""}</div></div></div>
   <div style={{display:"flex",gap:7,flexWrap:"wrap"}}><button className="btn-ghost" onClick={()=>setActive("home")}>Home</button>{services.length>0&&<button className="btn-ghost" onClick={()=>setActive("services")}>Services</button>}{showMenu&&<button className="btn-ghost" onClick={()=>setActive("menu")}>Menu</button>}{feature.feedback&&<button className="btn-ghost" onClick={()=>setActive("feedback")}>Reviews</button>}</div>
  </header>
  <section className="hero" style={{background:"radial-gradient(circle at 84% 18%,rgba(255,255,255,.22),transparent 26%),linear-gradient(115deg,#172554 0%,#4338ca 50%,#0f766e 100%)",padding:"clamp(28px,5vw,58px)",minHeight:300,display:"flex",flexDirection:"column",justifyContent:"center"}}>
   <div style={{fontSize:11,fontWeight:800,letterSpacing:".16em",textTransform:"uppercase",opacity:.85}}>{categoryLabel}{businessTypeLabel?" / "+businessTypeLabel:""} · CUSTOMER EXPERIENCE</div>
   <h1 style={{maxWidth:850,marginTop:18}}>{business.name}</h1>
   <p style={{fontSize:16,maxWidth:680}}>{business.description||"Professional service, personal attention. Discover what we offer and connect with our team when you are ready."}</p>
   <div style={{display:"flex",gap:10,flexWrap:"wrap",marginTop:24}}>
    {feature.ai_voice&&<button style={{background:"#fff",color:"#3730a3",borderRadius:999,padding:"13px 19px",boxShadow:"0 8px 22px #10104422"}} onClick={startTeamCall}>☎ Talk to our team</button>}
    {feature.bookings&&<button style={{background:"rgba(255,255,255,.14)",color:"#fff",border:"1px solid rgba(255,255,255,.4)",borderRadius:999,padding:"13px 19px"}} onClick={startTeamCall}>▦ Book a consultation</button>}
    {services.length>0&&<button style={{background:"rgba(255,255,255,.14)",color:"#fff",border:"1px solid rgba(255,255,255,.4)",borderRadius:999,padding:"13px 19px"}} onClick={()=>setActive("services")}>Explore services ↓</button>}
    {feature.ai_chat&&<button style={{background:"rgba(255,255,255,.14)",color:"#fff",border:"1px solid rgba(255,255,255,.4)",borderRadius:999,padding:"13px 19px"}} onClick={()=>location.href="/customer/assistant?business="+encodeURIComponent(business.slug)}>✦ Ask AI</button>}
   </div>
   {order&&<div style={{marginTop:22,background:"rgba(255,255,255,.13)",border:"1px solid rgba(255,255,255,.22)",borderRadius:14,padding:14,maxWidth:420,color:"#fff"}}><strong>Order #{order.id.slice(0,8)}</strong><div style={{marginTop:6,fontSize:12}}>{order.status.replace("_"," ").toUpperCase()} · {order.status==="pending"?"Order received":order.status==="confirmed"?"Confirmed":order.status==="preparing"?"In preparation":order.status==="ready"?"Ready":order.status==="served"?"Served":"Completed"}</div></div>}
  </section>
  <section style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:12,margin:"18px 0 26px"}}>
   {feature.ai_voice&&<button onClick={startTeamCall} style={{textAlign:"left",background:"#fff",color:"#1e293b",border:"1px solid #e1e7f3",borderRadius:18,padding:18,boxShadow:"0 8px 24px #1e293b08"}}><span style={{fontSize:24}}>☎️</span><div style={{fontWeight:800,marginTop:10}}>Talk to our team</div><div style={{fontSize:12,color:"#73809a",fontWeight:500,marginTop:4}}>Get help from our team</div></button>}
   {feature.bookings&&<button onClick={startTeamCall} style={{textAlign:"left",background:"linear-gradient(135deg,#f0fdfa,#ecfeff)",color:"#134e4a",border:"1px solid #bcebe5",borderRadius:18,padding:18}}><span style={{fontSize:24}}>🗓️</span><div style={{fontWeight:800,marginTop:10}}>Appointments</div><div style={{fontSize:12,opacity:.8,fontWeight:500,marginTop:4}}>Discuss a time that works for you</div></button>}
   {services.length>0&&<button onClick={()=>setActive("services")} style={{textAlign:"left",background:"linear-gradient(135deg,#eef2ff,#f5f3ff)",color:"#3730a3",border:"1px solid #dcd7ff",borderRadius:18,padding:18}}><span style={{fontSize:24}}>✦</span><div style={{fontWeight:800,marginTop:10}}>Services</div><div style={{fontSize:12,opacity:.8,fontWeight:500,marginTop:4}}>{services.length} services available</div></button>}
   {feature.online_payment&&<div style={{background:"linear-gradient(135deg,#fff7ed,#fffbeb)",color:"#92400e",border:"1px solid #fde5bd",borderRadius:18,padding:18}}><span style={{fontSize:24}}>⌁</span><div style={{fontWeight:800,marginTop:10}}>Secure payments</div><div style={{fontSize:12,opacity:.8,marginTop:4}}>Available when a bill or payment request is created</div></div>}
   {feature.feedback&&<button onClick={()=>setActive("feedback")} style={{textAlign:"left",background:"linear-gradient(135deg,#fdf2f8,#fff1f2)",color:"#9d174d",border:"1px solid #fbcfe8",borderRadius:18,padding:18}}><span style={{fontSize:24}}>☆</span><div style={{fontWeight:800,marginTop:10}}>Share feedback</div><div style={{fontSize:12,opacity:.8,fontWeight:500,marginTop:4}}>Help us improve your experience</div></button>}
  </section>
  <div style={{display:"flex",justifyContent:"space-between",alignItems:"end",gap:12,flexWrap:"wrap",margin:"24px 0 8px"}}><div><div style={{fontSize:11,color:"#6366f1",fontWeight:800,letterSpacing:".14em"}}>YOUR EXPERIENCE</div><h2 style={{fontSize:23,margin:"7px 0",color:"#17213a"}}>{isHospitality?"Everything for your visit":"How can we help you today?"}</h2><p style={{margin:0,fontSize:13,color:"#73809a"}}>{isHospitality?"Convenient service, ordering and support in one place.":"Explore our services, ask a question or connect with our team."}</p></div></div>
  <nav className="grid" style={{gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))",marginTop:12}}>
   <button className="card" onClick={()=>setActive("home")} style={{color:"#27314d",background:"#fff",border:"1px solid #e2e8f0"}}>⌂ Overview</button>
   {services.length>0&&<button className="card" onClick={()=>setActive("services")} style={{color:"#27314d",background:"#fff",border:"1px solid #e2e8f0"}}>✦ Services</button>}
   {showMenu&&<button className="card" onClick={()=>setActive("menu")} style={{color:"#27314d",background:"#fff",border:"1px solid #e2e8f0"}}>📖 Menu</button>}
   {showGames&&<button className="card" onClick={()=>setActive("games")} style={{color:"#27314d",background:"#fff",border:"1px solid #e2e8f0"}}>🎮 Play</button>}
   {feature.ai_voice&&<button className="card" onClick={startTeamCall} style={{color:"#27314d",background:"#fff",border:"1px solid #e2e8f0"}}>☎ Call</button>}
   {feature.ai_chat&&<button className="card" onClick={()=>location.href="/customer/assistant?business="+encodeURIComponent(business.slug)} style={{color:"#27314d",background:"#fff",border:"1px solid #e2e8f0"}}>✦ Ask AI</button>}
   {showTableTools&&<button className="card" onClick={()=>callWaiter("waiter")} style={{color:"#27314d",background:"#fff",border:"1px solid #e2e8f0"}}>🔔 Call Waiter</button>}
   {order&&<button className="card" onClick={()=>setActive("bill")} style={{color:"#27314d",background:"#fff",border:"1px solid #e2e8f0"}}>▣ Bill</button>}
  </nav>

  {active==="home"&&<section className="grid">
   {showTableTools&&<article className="card"><h2>🍽️ Your table</h2><p>{context?context:"Scan your table QR to attach this request to your table."}</p>{waiter&&<p>🔔 {waiter.status||"requested"}{waiter.assigned_staff_name?" · "+waiter.assigned_staff_name:""}</p>}<div style={{display:"flex",gap:8,flexWrap:"wrap"}}><button onClick={()=>callWaiter("waiter")}>Call waiter</button><button onClick={()=>callWaiter("water")}>💧 Water</button><button onClick={()=>callWaiter("cutlery")}>🍴 Cutlery</button><button onClick={()=>callWaiter("clear_table")}>🧹 Clear table</button></div></article>}
   {showGames&&<article className="card"><h2>🎮 Relax & play</h2><p>Take a short break with our mini games.</p><button onClick={()=>setActive("games")}>Play now</button></article>}
   {showMenu&&<article className="card"><h2>📖 Menu & ordering</h2><p>{items.length?items.length+" items available":"Menu is being prepared."}</p><button onClick={()=>setActive("menu")}>Browse menu</button></article>}
   {services.length>0&&<article className="card" style={{background:"linear-gradient(135deg,#fff,#f0fdfa)",borderColor:"#d2eee9"}}><h2>✦ Our services</h2><p>Find the right service for your needs.</p><button onClick={()=>setActive("services")} style={{background:"linear-gradient(135deg,#4f46e5,#0f766e)"}}>Explore services</button></article>}
   {feature.ai_chat&&<article className="card"><h2>✦ AI assistant</h2><p>Ask about our services, timings or next steps.</p><button onClick={()=>location.href="/customer/assistant?business="+encodeURIComponent(business.slug)} style={{background:"linear-gradient(135deg,#4f46e5,#0f766e)"}}>Ask AI</button></article>}
   {feature.bookings&&<article className="card"><h2>🗓️ Need an appointment?</h2><p>Speak with our team to discuss availability and booking.</p><button onClick={startTeamCall} style={{background:"linear-gradient(135deg,#4f46e5,#0f766e)"}}>Discuss appointment</button></article>}
  </section>
  {active==="services"&&<section className="card" style={{padding:"clamp(18px,3vw,30px)"}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12}}><div><div style={{fontSize:11,color:"#6366f1",fontWeight:800,letterSpacing:".14em"}}>WHAT WE DO</div><h2 style={{fontSize:24,margin:"6px 0"}}>Services from {business.name}</h2></div><button className="btn-ghost" onClick={()=>setActive("home")}>Back</button></div><div className="grid">{services.map((s:any)=><article key={s.id} className="card" style={{background:"linear-gradient(145deg,#fff,#f4f7ff)",borderColor:"#e0e7ff"}}><div style={{width:42,height:42,display:"grid",placeItems:"center",borderRadius:13,background:"#e0e7ff",color:"#4338ca",fontSize:21}}>✦</div><h3 style={{marginTop:14,fontSize:16}}>{s.name}</h3><p>{s.description||"Personalised service from our team."}</p>{s.duration_minutes&&<p style={{fontSize:12,color:"#6b7280"}}>Duration · {s.duration_minutes} minutes</p>}{s.price!==null&&s.price!==undefined&&<p style={{fontWeight:800,color:"#0f766e"}}>{s.currency||"INR"} {s.price}</p>}<button style={{marginTop:8,background:"linear-gradient(135deg,#4f46e5,#0f766e)"}} onClick={startTeamCall}>{feature.bookings?"Ask about booking":"Ask about this service"}</button></article>)}</div></section>}

  {active==="menu"&&<section className="card"><div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"center"}}><h2>📖 Digital Menu</h2><button onClick={()=>setActive("home")}>Back</button></div>{cats.map((cat:any)=><div key={cat.id}><h3>{cat.name}</h3><div className="grid">{items.filter(x=>x.category_id===cat.id).map(x=><article className="card" key={x.id}><h3>{x.name}</h3><p>{x.description}</p><strong>₹{x.price}</strong><div><button onClick={()=>remove(x.id)}>-</button><span style={{padding:"0 12px"}}>{cart[x.id]||0}</span><button onClick={()=>add(x.id)}>+</button></div></article>)}</div></div>)}{items.filter(x=>!x.category_id).map(x=><article className="card" key={x.id}><h3>{x.name}</h3><p>{x.description}</p><strong>₹{x.price}</strong><button onClick={()=>add(x.id)}>Add</button></article>)}{cartItems.length>0&&<div className="card"><strong>Cart: ₹{total}</strong><button onClick={placeOrder}>Place order</button></div>}</section>}

  {active==="games"&&<section className="card"><h2>🎮 Relax & Play</h2>{!game?<div className="grid">{gameNames.map(x=><button className="card" key={x} onClick={()=>playGame(x)}>{gameLabels[x]}</button>)}</div>:<div className="card"><h3>{gameLabels[game]}</h3><p>Score: <strong>{gameScore}</strong></p>
 {game==="dino"&&<><p>Jump over the cactus. Each jump earns distance.</p><button style={{fontSize:26,padding:28}} onClick={()=>gameAction("jump")}>🦖 JUMP</button></>}
 {game==="flappy"&&<><p>Keep the bird flying through the pipes.</p><button style={{fontSize:26,padding:28}} onClick={()=>gameAction("flap")}>🐦 FLAP</button></>}
 {game==="tap"&&<><p>Tap the target as quickly as possible.</p><div className="grid" style={{gridTemplateColumns:"repeat(3,1fr)"}}>{Array.from({length:9},(_,i)=><button key={i} style={{fontSize:24,padding:20}} onClick={()=>i===gameData.target&&gameAction("target")}>{i===gameData.target?"🎯":"·"}</button>)}</div></>}
 {game==="brick"&&<><p>Break every brick.</p><div className="grid" style={{gridTemplateColumns:"repeat(4,1fr)"}}>{gameData.bricks.map((on:boolean,i:number)=><button key={i} disabled={!on} onClick={()=>gameAction(String(i))}>{on?"🧱":"✨"}</button>)}</div></>}
 {game==="snake"&&<><p>Collect points with the snake controls.</p><div style={{display:"grid",gridTemplateColumns:"repeat(3,70px)",justifyContent:"center",gap:6}}><span/><button onClick={()=>gameAction("up")}>⬆️</button><span/><button onClick={()=>gameAction("left")}>⬅️</button><button onClick={()=>gameAction("eat")}>🐍</button><button onClick={()=>gameAction("right")}>➡️</button><span/><button onClick={()=>gameAction("down")}>⬇️</button><span/></div></>}
 {game==="2048"&&<><p>Combine moves to build your score.</p><div className="grid" style={{gridTemplateColumns:"repeat(3,1fr)"}}><button onClick={()=>gameAction("up")}>⬆️</button><button onClick={()=>gameAction("left")}>⬅️</button><button onClick={()=>gameAction("right")}>➡️</button><button onClick={()=>gameAction("down")}>⬇️</button></div><p>Moves: {gameData.moves}</p></>}
 <button onClick={()=>{saveGame();setGame(null)}}>Finish game</button><button onClick={()=>setGame(null)}>Back to games</button>{gamePoints>0&&<p>🎁 +{gamePoints} loyalty points</p>}</div>}</section>}

  {active==="bill"&&<section className="card"><h2>💳 Your bill</h2>{order?.bill?<><p>Order total: <strong>₹{order.bill.total}</strong></p><p>Status: {order.bill.status}</p>{business.features?.online_payment&&<button onClick={payBill}>Pay now</button>}</>:<p>Your bill is generated automatically when the order is completed.</p>}<button onClick={()=>setActive("menu")}>Order more</button></section>}

  {active==="feedback"&&<section className="card"><h2>⭐ How was your experience?</h2>{feedbackSent?<p>Thank you for your feedback.</p>:<><div style={{fontSize:32}}>{[1,2,3,4,5].map(n=><button key={n} onClick={()=>setFeedback(n)} aria-label={n+" stars"}>{n<=feedback?"★":"☆"}</button>)}</div><textarea placeholder="Tell us about your experience (optional)" value={comment} onChange={e=>setComment(e.target.value)}/><button onClick={submitFeedback}>Submit feedback</button><p>After feedback, we'll offer the configured Google review link.</p></>}</section>}

  {callOpen&&business&&<VoiceCallModal key={callInstance}
    slug={business.slug}
    businessName={business.name}
    existingCustomerId={storedCustomerId||undefined}
    onCustomerIdentified={(id)=>{
      setStoredCustomerId(id);
      setCustomerId(id);
      try{localStorage.setItem("cust:last-business",business.slug);}catch{}
    }}
    onClose={()=>setCallOpen(false)}
  />}

  <p aria-live="polite">{status}</p>
 </main>;
}