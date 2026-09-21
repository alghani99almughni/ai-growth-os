"use client";
import {useEffect,useMemo,useState} from "react";

const api=()=>process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
type Item={id:string;category_id?:string;name:string;description?:string;price:number;currency?:string};
type Cart=Record<string,number>;

const gameNames=["dino","snake","brick","flappy","tap","2048"];
const gameLabels:Record<string,string>={dino:"🦖 Dino Run",snake:"🐍 Snake",brick:"🧱 Brick Breaker",flappy:"🐦 Flappy",tap:"🎯 Tap Target","2048":"🔢 2048"};

export default function Customer(){
 const [slug,setSlug]=useState(""),[business,setBusiness]=useState<any>(null),[context,setContext]=useState(""),[customerId,setCustomerId]=useState(""),[cart,setCart]=useState<Cart>({}),[order,setOrder]=useState<any>(null),[menuOpen,setMenuOpen]=useState(false),[game,setGame]=useState<string|null>(null),[gameScore,setGameScore]=useState(0),[waiter,setWaiter]=useState<any>(null),[feedback,setFeedback]=useState(0),[comment,setComment]=useState(""),[feedbackSent,setFeedbackSent]=useState(false),[status,setStatus]=useState(""),[active,setActive]=useState("home"),[gamePoints,setGamePoints]=useState(0);
 const [customerName,setCustomerName]=useState("");
 useEffect(()=>{const p=new URLSearchParams(location.search);setSlug(p.get("business")||"");setContext(p.get("context")||"");setCustomerId(p.get("customer")||"")},[]);
 useEffect(()=>{if(!slug)return;fetch(api()+"/api/v1/public/business/"+encodeURIComponent(slug)).then(r=>r.json()).then(d=>{if(d.id)setBusiness(d);else setStatus(d.detail||"Business not found")})},[slug]);
 useEffect(()=>{if(!order||!business)return;const id=window.setInterval(()=>fetch(api()+"/api/v1/public/business/"+business.slug+"/orders/"+order.id).then(r=>r.json()).then(setOrder).catch(()=>{}),5000);return()=>clearInterval(id)},[order?.id,business?.slug]);
 const items:Item[]=business?.menu?.items||[];
 const cats=business?.menu?.categories||[];
 const cartItems=useMemo(()=>items.filter(x=>cart[x.id]).map(x=>({...x,quantity:cart[x.id]})),[items,cart]);
 const total=cartItems.reduce((s,x)=>s+x.price*x.quantity,0);
 function add(id:string){setCart(c=>({...c,[id]:(c[id]||0)+1}))}
 function remove(id:string){setCart(c=>{const n={...c};n[id]=(n[id]||0)-1;if(n[id]<=0)delete n[id];return n})}
 async function placeOrder(){if(!business||!cartItems.length)return;setStatus("Placing order…");const r=await fetch(api()+"/api/v1/public/business/"+business.slug+"/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({items:cartItems.map(x=>({menu_item_id:x.id,quantity:x.quantity})),context_token:context||undefined,customer_id:customerId||undefined})});const d=await r.json();if(!r.ok){setStatus(d.detail||"Unable to place order");return}setOrder(d);setCart({});setActive("home");setStatus("Order placed successfully");}
 async function callWaiter(type="waiter"){if(!business)return;const r=await fetch(api()+"/api/v1/public/business/"+business.slug+"/service-requests",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({request_type:type,context_token:context||undefined,customer_id:customerId||undefined})});const d=await r.json();if(r.ok){setWaiter(d);setStatus("Request sent to the team");}else setStatus(d.detail||"Unable to send request")}
 async function submitFeedback(){if(!business||!feedback)return;const r=await fetch(api()+"/api/v1/public/business/"+business.slug+"/feedback",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({order_id:order?.id,customer_id:customerId||undefined,rating:feedback,comment})});const d=await r.json();if(r.ok){setFeedbackSent(true);if(d.google_review_url)window.open(d.google_review_url,"_blank","noopener,noreferrer");}}
 async function payBill(){if(!business||!order?.bill)return;setStatus("Preparing secure payment…");const r=await fetch(api()+"/api/v1/public/business/"+business.slug+"/bills/"+order.bill.id+"/payment-order",{method:"POST"});const d=await r.json();if(!r.ok){setStatus(d.detail||"Payment unavailable");return}const s=document.createElement("script");s.src="https://checkout.razorpay.com/v1/checkout.js";s.onload=()=>{const rz=new (window as any).Razorpay({key:d.key_id,amount:d.amount,currency:d.currency,name:business.name,order_id:d.razorpay_order_id,handler:async(res:any)=>{const v=await fetch(api()+"/api/v1/public/business/"+business.slug+"/bills/"+order.bill.id+"/verify-payment",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({razorpay_order_id:res.razorpay_order_id,razorpay_payment_id:res.razorpay_payment_id,razorpay_signature:res.razorpay_signature})});const vd=await v.json();setStatus(v.ok?"Payment successful":"Payment verification failed");if(v.ok)setOrder({...order,bill:{...order.bill,status:"paid"}})}});rz.open()};document.body.appendChild(s)}
 async function saveGame(){if(!business||!game)return;const r=await fetch(api()+"/api/v1/public/business/"+business.slug+"/games/"+game+"/score?score="+Math.max(0,Math.floor(gameScore))+(customerId?"&customer_id="+encodeURIComponent(customerId):" "),{method:"POST"});if(r.ok){const d=await r.json();setGamePoints(d.reward_points||0)}}
 function playGame(name:string){setGame(name);setGameScore(0);setGamePoints(0)}
 if(!business)return <main className="shell"><section className="hero"><p>AI GROWTH OS • CUSTOMER PWA</p><h1>{slug||"Your business experience"}</h1><p>{status||"Loading your experience…"}</p></section></main>;
 const delivered=order&&["served","completed"].includes(order.status);
 return <main className="shell">
  <section className="hero">
   <p>{business.industry?.toUpperCase()} • CUSTOMER EXPERIENCE</p>
   <h1>{business.name}</h1>
   <p>{business.description||"Welcome. Everything you need for your visit is here."}</p>
   {order&&<div className="card"><strong>🍽️ Order #{order.id.slice(0,8)}</strong><div className="statusline"><span className={order.status==="completed"?"done":"live"}>{order.status.replace("_"," ").toUpperCase()}</span></div><small>{order.status==="pending"?"Order received":order.status==="confirmed"?"Kitchen confirmed":order.status==="preparing"?"Your food is being prepared":order.status==="ready"?"Your order is ready":order.status==="served"?"Delivered to your table":"Order completed"}</small></div>}
  </section>

  <nav className="grid" style={{gridTemplateColumns:"repeat(auto-fit,minmax(120px,1fr))"}}>
   <button className="card" onClick={()=>setActive("home")}>🏠 Home</button>
   {business.features?.digital_menu&&<button className="card" onClick={()=>setActive("menu")}>📖 Menu</button>}
   {business.features?.games&&<button className="card" onClick={()=>setActive("games")}>🎮 Play</button>}
   {business.features?.call_waiter&&<button className="card" onClick={()=>callWaiter("waiter")}>🔔 Call Waiter</button>}
   {order&&<button className="card" onClick={()=>setActive("bill")}>💳 Bill</button>}
   {delivered&&<button className="card" onClick={()=>setActive("feedback")}>⭐ Feedback</button>}
  </nav>

  {active==="home"&&<section className="grid">
   <article className="card"><h2>🍽️ Your table</h2><p>{context?context:"Table context will appear here when you scan a table QR."}</p>{waiter&&<p>🔔 {waiter.status||"requested"}{waiter.assigned_staff_name?" • "+waiter.assigned_staff_name:""}</p>}{business.features?.call_waiter&&<div style={{display:"flex",gap:8,flexWrap:"wrap"}}><button onClick={()=>callWaiter("waiter")}>Call waiter</button><button onClick={()=>callWaiter("water")}>💧 Water</button><button onClick={()=>callWaiter("cutlery")}>🍴 Cutlery</button><button onClick={()=>callWaiter("clear_table")}>🧹 Clear table</button></div>}</article>
   {business.features?.games&&<article className="card"><h2>🎮 Relax & play</h2><p>All six mini games run locally in your browser.</p><button onClick={()=>setActive("games")}>Play now</button></article>}
   {business.features?.digital_menu&&<article className="card"><h2>📖 Menu</h2><p>{items.length?items.length+" items available":"Menu is being prepared."}</p><button onClick={()=>setActive("menu")}>Browse menu</button></article>}
   {business.features?.ai_chat&&<article className="card"><h2>🤖 AI Assistant</h2><p>Ask about the menu, order, business or anything you need.</p><button onClick={()=>location.href="/customer/assistant?business="+encodeURIComponent(business.slug)}>Ask AI</button></article>}
  </section>}

  {active==="menu"&&<section className="card"><div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"center"}}><h2>📖 Digital Menu</h2><button onClick={()=>setActive("home")}>Back</button></div>{cats.map((cat:any)=><div key={cat.id}><h3>{cat.name}</h3><div className="grid">{items.filter(x=>x.category_id===cat.id).map(x=><article className="card" key={x.id}><h3>{x.name}</h3><p>{x.description}</p><strong>₹{x.price}</strong><div><button onClick={()=>remove(x.id)}>-</button><span style={{padding:"0 12px"}}>{cart[x.id]||0}</span><button onClick={()=>add(x.id)}>+</button></div></article>)}</div></div>)}{items.filter(x=>!x.category_id).map(x=><article className="card" key={x.id}><h3>{x.name}</h3><p>{x.description}</p><strong>₹{x.price}</strong><button onClick={()=>add(x.id)}>Add</button></article>)}{cartItems.length>0&&<div className="card"><strong>Cart: ₹{total}</strong><button onClick={placeOrder}>Place order</button></div>}</section>}

  {active==="games"&&<section className="card"><h2>🎮 Relax & Play</h2>{!game?<div className="grid">{gameNames.map(x=><button className="card" key={x} onClick={()=>playGame(x)}>{gameLabels[x]}</button>)}</div>:<div className="card"><h3>{gameLabels[game]}</h3><p>Score: <strong>{gameScore}</strong></p><div style={{minHeight:120,display:"grid",placeItems:"center"}}><button style={{fontSize:28,padding:30}} onClick={()=>setGameScore(s=>s+1)}>TAP / PLAY</button></div><button onClick={()=>{saveGame();setGame(null)}}>Finish game</button><button onClick={()=>setGame(null)}>Back to games</button>{gamePoints>0&&<p>🎁 +{gamePoints} loyalty points</p>}</div>}</section>}

  {active==="bill"&&<section className="card"><h2>💳 Your bill</h2>{order?.bill?<><p>Order total: <strong>₹{order.bill.total}</strong></p><p>Status: {order.bill.status}</p>{business.features?.online_payment&&<button onClick={payBill}>Pay now</button>}</>:<p>Your bill is generated automatically when the order is completed.</p>}<button onClick={()=>setActive("menu")}>Order more</button></section>}

  {active==="feedback"&&<section className="card"><h2>⭐ How was your experience?</h2>{feedbackSent?<p>Thank you for your feedback.</p>:<><div style={{fontSize:32}}>{[1,2,3,4,5].map(n=><button key={n} onClick={()=>setFeedback(n)} aria-label={n+" stars"}>{n<=feedback?"★":"☆"}</button>)}</div><textarea placeholder="Tell us about your experience (optional)" value={comment} onChange={e=>setComment(e.target.value)}/><button onClick={submitFeedback}>Submit feedback</button><p>After feedback, we'll offer the configured Google review link.</p></>}</section>}

  <p aria-live="polite">{status}</p>
 </main>;
}
