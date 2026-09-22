import type {Metadata} from "next";

export async function generateMetadata({params}:{params:{slug:string}}):Promise<Metadata>{
  const base=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
  let name=params.slug;
  try{
    const r=await fetch(base+"/api/v1/public/business/"+encodeURIComponent(params.slug),{cache:"no-store"});
    if(r.ok){const b=await r.json();name=b?.name||name;}
  }catch{}
  return {
    title:name+" | Customer",
    description:"Customer experience for "+name,
    manifest:"/pwa/"+params.slug+"/manifest.webmanifest"
  };
}

export default function TenantPwaLayout({children}:{children:React.ReactNode}){
  return children;
}
