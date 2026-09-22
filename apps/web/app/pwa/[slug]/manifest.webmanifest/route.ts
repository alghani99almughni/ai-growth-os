import {NextResponse} from "next/server";

export async function GET(request:Request,{params}:{params:{slug:string}}){
  const api=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
  let business:any=null;
  try{
    const r=await fetch(api+"/api/v1/public/business/"+encodeURIComponent(params.slug),{cache:"no-store"});
    if(r.ok) business=await r.json();
  }catch{}
  const name=business?.name||params.slug;
  const industry=String(business?.industry||"business").toLowerCase();
  const appUrl=new URL(request.url).origin;
  return NextResponse.json({
    id:"/pwa/"+params.slug,
    name,
    short_name:name.slice(0,20),
    description:business?.description||"Customer experience",
    start_url:"/pwa/"+params.slug,
    scope:"/pwa/"+params.slug,
    display:"standalone",
    orientation:"portrait",
    background_color:"#f7f4ec",
    theme_color:"#0d4f3d",
    categories:[industry,"business"],
    icons:[
      {src:appUrl+"/ss-nutritions/icon.svg",sizes:"192x192",type:"image/svg+xml",purpose:"any maskable"},
      {src:appUrl+"/ss-nutritions/icon.svg",sizes:"512x512",type:"image/svg+xml",purpose:"any maskable"}
    ]
  },{headers:{"Content-Type":"application/manifest+json"}});
}
