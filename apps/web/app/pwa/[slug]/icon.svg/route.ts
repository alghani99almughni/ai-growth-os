import {NextResponse} from "next/server";
export async function GET(request:Request,{params}:{params:Promise<{slug:string}>}){
 const {slug}=await params; const api=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000"; let name=slug.replace(/[-_]+/g," ");
 try{const r=await fetch(api+"/api/v1/public/business/"+encodeURIComponent(slug),{cache:"no-store"});if(r.ok){const b=await r.json();name=b?.name||name;}}catch{}
 const initials=name.trim().split(/\s+/).slice(0,2).map((x:string)=>x[0]?.toUpperCase()).join("")||"AI";
 const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="112" fill="#0d4f3d"/><text x="256" y="292" text-anchor="middle" font-family="Arial,sans-serif" font-size="190" font-weight="700" fill="#fff">${initials}</text></svg>`;
 return new NextResponse(svg,{headers:{"Content-Type":"image/svg+xml","Cache-Control":"public, max-age=300"}});
}