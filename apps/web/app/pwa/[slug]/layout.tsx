import type {Metadata} from "next";

export async function generateMetadata({params}:{params:Promise<{slug:string}>}):Promise<Metadata>{
  const {slug}=await params;
  const base=process.env.NEXT_PUBLIC_API_URL||"http://localhost:8000";
  let name=slug;
  try{
    const r=await fetch(base+"/api/v1/public/business/"+encodeURIComponent(slug),{cache:"no-store"});
    if(r.ok){const b=await r.json();name=b?.name||name;}
  }catch{}
  return {
    title:name+" | Customer",
    description:"Customer experience for "+name,
    manifest:"/pwa/"+slug+"/manifest.webmanifest"
  };
}

export default function TenantPwaLayout({children}:{children:React.ReactNode}){
  return children;
}
