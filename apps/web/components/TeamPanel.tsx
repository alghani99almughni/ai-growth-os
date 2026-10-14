"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Staff = { id:string; name:string; user_id?:string|null; department_id?:string|null; department_name?:string|null; email?:string|null; role?:string|null; skills:string|null; service_ids?:string[]; is_active:boolean; is_available:boolean };
type Department = {id:string;name:string;description?:string;skills:string;is_active:boolean};
type Role = {id:string;name:string;permissions:string[];is_system:boolean};
type Service = {id:string;name:string;is_active:boolean};
const PERMISSIONS = [
  ["dashboard.view","Dashboard"],["customers.view","Customers"],["customers.manage","Manage customers"],
  ["bookings.view","Bookings"],["bookings.manage","Manage bookings"],["services.view","Services"],
  ["services.manage","Manage services"],["calls.view","Calls"],["calls.manage","Manage calls"],
  ["campaigns.view","Marketing campaigns"],["campaigns.manage","Send campaigns"],
  ["communications.view","WhatsApp & email inbox"],["communications.reply","Reply to messages"],
  ["reports.view","Reports"],["team.manage","Manage team"],["settings.manage","Business settings"]
];
export default function TeamPanel({tenantId,token}:{tenantId:string;token:string}) {
  const [items,setItems]=useState<Staff[]>([]);
  const [departments,setDepartments]=useState<Department[]>([]);
  const [roles,setRoles]=useState<Role[]>([]);
  const [services,setServices]=useState<Service[]>([]);
  const [selectedServiceIds,setSelectedServiceIds]=useState<string[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState("");
  const [status,setStatus]=useState("");
  const [tab,setTab]=useState<"members"|"roles"|"departments">("members");
  const [staff,setStaff]=useState({name:"",email:"",password:"",role:"",department_id:"",skills:""});
  const [roleName,setRoleName]=useState("");
  const [permissions,setPermissions]=useState<string[]>(["dashboard.view"]);
  const [dept,setDept]=useState({name:"",description:"",skills:""});
  const [busy,setBusy]=useState(false);
  const headers=()=>({"Content-Type":"application/json",Authorization:"Bearer "+token});
  async function request(path:string,init?:RequestInit) {
    const r=await fetch(api()+path,{...init,headers:{...headers(),...(init?.headers||{})},cache:"no-store"});
    const raw=await r.text(); let x:any={}; try{x=JSON.parse(raw)}catch{}
    if(!r.ok) throw new Error(x?.detail||"Request failed"); return x;
  }
  async function loadAll() {
    setLoading(true);setError("");
    try {
      const [s,d,r,sv]=await Promise.all([
        request(`/api/v1/tenants/${tenantId}/staff`),
        request(`/api/v1/tenants/${tenantId}/departments`),
        request(`/api/v1/tenants/${tenantId}/roles`)
      ]);
      setItems(s.items||[]);setDepartments(d.items||[]);setRoles(r.items||[]);setServices((sv.items||[]).filter((x:Service)=>x.is_active));
      if(!staff.role && (r.items||[]).length) setStaff(v=>({...v,role:r.items[0].name}));
    } catch(e:any){setError(e.message||"Could not load team configuration")}
    setLoading(false);
  }
  useEffect(()=>{if(tenantId)void loadAll()},[tenantId]);
  async function createStaff(e:any) {
    e.preventDefault();setBusy(true);setStatus("");setError("");
    try {
      await request(`/api/v1/tenants/${tenantId}/staff`,{method:"POST",body:JSON.stringify({...staff,service_ids:selectedServiceIds,skills:staff.skills.split(",").map(x=>x.trim()).filter(Boolean).join(",")})});
      setStatus("Team member created. They can sign in using the email and password you set.");
      setStaff({name:"",email:"",password:"",role:roles[0]?.name||"",department_id:"",skills:""});setSelectedServiceIds([]);await loadAll();
    } catch(e:any){setError(e.message||"Could not create team member")} setBusy(false);
  }
  async function createRole(e:any) {
    e.preventDefault();setBusy(true);setError("");setStatus("");
    try {await request(`/api/v1/tenants/${tenantId}/roles`,{method:"POST",body:JSON.stringify({name:roleName,permissions})});setRoleName("");setStatus("Role and permissions saved.");await loadAll();}
    catch(e:any){setError(e.message||"Could not create role")}setBusy(false);
  }
  async function createDepartment(e:any) {
    e.preventDefault();setBusy(true);setError("");setStatus("");
    try {await request(`/api/v1/tenants/${tenantId}/departments`,{method:"POST",body:JSON.stringify(dept)});setDept({name:"",description:"",skills:""});setStatus("Department created.");await loadAll();}
    catch(e:any){setError(e.message||"Could not create department")}setBusy(false);
  }
  async function toggleServiceAssignment(s:Staff,serviceId:string,checked:boolean) {
    const current=s.service_ids||[];
    const next=checked?[...new Set([...current,serviceId])]:current.filter(id=>id!==serviceId);
    try {await request(`/api/v1/tenants/${tenantId}/staff/${s.id}`,{method:"PATCH",body:JSON.stringify({service_ids:next})});await loadAll();}
    catch(e:any){setError(e.message||"Could not update service assignment")}
  }
  async function toggleStaff(s:Staff,field:"is_active"|"is_available",value:boolean) {
    try {await request(`/api/v1/tenants/${tenantId}/staff/${s.id}`,{method:"PATCH",body:JSON.stringify({[field]:value})});await loadAll();}
    catch(e:any){setError(e.message||"Could not update member")}
  }
  const input:React.CSSProperties={width:"100%",boxSizing:"border-box",padding:"10px 12px",border:"1px solid #d8deea",borderRadius:8,marginTop:5,color:"#17213a",background:"#fff"};
  const btn:React.CSSProperties={padding:"9px 13px",borderRadius:8,border:"1px solid #d8deea",background:"#fff",cursor:"pointer",fontWeight:600};
  return <section className="card">
    <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,flexWrap:"wrap"}}>
      <div><h2 style={{margin:0}}>Team & access control</h2><p style={{margin:"5px 0 0",color:"#75839a",fontSize:13}}>Create dashboard logins, assign roles, departments, and service responsibilities.</p></div>
      <button style={btn} onClick={()=>void loadAll()} disabled={loading}>{loading?"Loading…":"Refresh"}</button>
    </div>
    <div style={{display:"flex",gap:8,flexWrap:"wrap",margin:"18px 0"}}>
      {([{id:"members",label:"Team members"},{id:"roles",label:"Roles & permissions"},{id:"departments",label:"Departments / services"}] as const).map(t=><button key={t.id} style={{...btn,background:tab===t.id?"#4f46e5":"#fff",color:tab===t.id?"#fff":"#344054",borderColor:tab===t.id?"#4f46e5":"#d8deea"}} onClick={()=>setTab(t.id)}>{t.label}</button>)}
    </div>
    {error&&<p style={{padding:10,borderRadius:8,background:"#fff1f0",color:"#b42318"}}>{error}</p>}
    {status&&<p style={{padding:10,borderRadius:8,background:"#ecfdf3",color:"#067647"}}>{status}</p>}
    {tab==="members"&&<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))",gap:20}}>
      <form onSubmit={createStaff} style={{border:"1px solid #e8ecf3",borderRadius:12,padding:16}}>
        <h3 style={{marginTop:0}}>Add team member / dashboard login</h3>
        <label>Full name<input required minLength={2} value={staff.name} onChange={e=>setStaff({...staff,name:e.target.value})} style={input}/></label>
        <label style={{display:"block",marginTop:10}}>Login email<input required type="email" value={staff.email} onChange={e=>setStaff({...staff,email:e.target.value})} style={input}/></label>
        <label style={{display:"block",marginTop:10}}>Temporary password<input required minLength={8} type="password" value={staff.password} onChange={e=>setStaff({...staff,password:e.target.value})} style={input}/></label>
        <label style={{display:"block",marginTop:10}}>Role<select required value={staff.role} onChange={e=>setStaff({...staff,role:e.target.value})} style={input}><option value="">Select a role…</option>{roles.map(r=><option key={r.id} value={r.name}>{r.name}</option>)}</select></label>
        <label style={{display:"block",marginTop:10}}>Department<select value={staff.department_id} onChange={e=>setStaff({...staff,department_id:e.target.value})} style={input}><option value="">Unassigned</option>{departments.map(d=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
        <div style={{marginTop:12}}><strong style={{fontSize:13}}>Map services to this member</strong>
          {services.length?services.map(s=><label key={s.id} style={{display:"flex",gap:8,alignItems:"center",marginTop:7,fontSize:13,color:"#344054"}}><input type="checkbox" checked={selectedServiceIds.includes(s.id)} onChange={e=>setSelectedServiceIds(ids=>e.target.checked?[...ids,s.id]:ids.filter(id=>id!==s.id))}/>{s.name}</label>):<p style={{fontSize:12,color:"#b54708"}}>Add services under Services first. You can still create a team member.</p>}
        </div>
        <label style={{display:"block",marginTop:10}}>Additional skills (optional, comma separated)<input value={staff.skills} onChange={e=>setStaff({...staff,skills:e.target.value})} placeholder="Customer support, follow-ups" style={input}/></label>
        <button disabled={busy||!roles.length} style={{...btn,marginTop:14,background:"#4f46e5",color:"#fff",borderColor:"#4f46e5"}}>{busy?"Saving…":"Create member & login"}</button>
        {!roles.length&&<p style={{fontSize:12,color:"#b54708"}}>Create a role first under Roles & permissions.</p>}
      </form>
      <div><h3 style={{marginTop:0}}>Current team ({items.length})</h3>{items.map(s=><article key={s.id} style={{border:"1px solid #e8ecf3",borderRadius:10,padding:13,marginBottom:10}}>
        <div style={{display:"flex",justifyContent:"space-between",gap:8}}><strong>{s.name}</strong><span style={{fontSize:12,color:s.is_active?"#067647":"#b42318"}}>{s.is_active?"Active":"Inactive"}</span></div>
        <p style={{margin:"5px 0",fontSize:13,color:"#667085"}}>{s.email||"No login email"} · {s.role||"staff"}</p>
        <p style={{margin:"5px 0",fontSize:12,color:"#667085"}}>{s.department_name||"No department"} · Skills: {s.skills||"Not assigned"}</p>
        <div style={{marginTop:9,paddingTop:8,borderTop:"1px solid #edf0f5"}}><strong style={{fontSize:12}}>Assigned services</strong>
          {services.length?services.map(service=><label key={service.id} style={{display:"inline-flex",gap:5,alignItems:"center",margin:"7px 12px 0 0",fontSize:12,color:"#344054"}}><input type="checkbox" checked={(s.service_ids||[]).includes(service.id)} onChange={e=>void toggleServiceAssignment(s,service.id,e.target.checked)}/>{service.name}</label>):<p style={{fontSize:12,color:"#667085"}}>No active services configured.</p>}
        </div>
        <div style={{display:"flex",gap:8,flexWrap:"wrap",marginTop:9}}><button style={btn} onClick={()=>void toggleStaff(s,"is_active",!s.is_active)}>{s.is_active?"Disable login":"Enable login"}</button><button style={btn} onClick={()=>void toggleStaff(s,"is_available",!s.is_available)}>{s.is_available?"Mark unavailable":"Mark available"}</button></div>
      </article>)}{!items.length&&!loading&&<p style={{color:"#75839a"}}>No team members yet. Create the first member using the form.</p>}</div>
    </div>}
    {tab==="roles"&&<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))",gap:20}}>
      <form onSubmit={createRole} style={{border:"1px solid #e8ecf3",borderRadius:12,padding:16}}>
        <h3 style={{marginTop:0}}>Create role</h3><label>Role name<input required minLength={2} value={roleName} onChange={e=>setRoleName(e.target.value)} placeholder="e.g. Receptionist, Sales, Nutritionist" style={input}/></label>
        <p style={{fontSize:12,color:"#667085"}}>Select the dashboard areas and actions this role is allowed to handle.</p>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:9}}>{PERMISSIONS.map(([key,label])=><label key={key} style={{display:"flex",gap:7,alignItems:"flex-start",fontSize:12,color:"#344054"}}><input type="checkbox" checked={permissions.includes(key)} onChange={e=>setPermissions(p=>e.target.checked?[...p,key]:p.filter(x=>x!==key))}/>{label}</label>)}</div>
        <button disabled={busy} style={{...btn,marginTop:14,background:"#4f46e5",color:"#fff",borderColor:"#4f46e5"}}>{busy?"Saving…":"Save role & permissions"}</button>
      </form>
      <div><h3 style={{marginTop:0}}>Configured roles</h3>{roles.map(r=><article key={r.id} style={{border:"1px solid #e8ecf3",borderRadius:10,padding:13,marginBottom:10}}><strong>{r.name}</strong>{r.is_system&&<span style={{marginLeft:8,fontSize:11,color:"#667085"}}>System</span>}<p style={{fontSize:12,color:"#667085",marginBottom:0}}>{(r.permissions||[]).map(p=>PERMISSIONS.find(x=>x[0]===p)?.[1]||p).join(" · ")||"No permissions selected"}</p></article>)}</div>
    </div>}
    {tab==="departments"&&<div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))",gap:20}}>
      <form onSubmit={createDepartment} style={{border:"1px solid #e8ecf3",borderRadius:12,padding:16}}><h3 style={{marginTop:0}}>Create department / service group</h3>
        <label>Name<input required minLength={2} value={dept.name} onChange={e=>setDept({...dept,name:e.target.value})} placeholder="Reception, Sales, Consultation" style={input}/></label>
        <label style={{display:"block",marginTop:10}}>Description<input value={dept.description} onChange={e=>setDept({...dept,description:e.target.value})} style={input}/></label>
        <label style={{display:"block",marginTop:10}}>Services handled (comma separated)<input value={dept.skills} onChange={e=>setDept({...dept,skills:e.target.value})} placeholder="Bookings, product enquiries, follow-ups" style={input}/></label>
        <button disabled={busy} style={{...btn,marginTop:14,background:"#4f46e5",color:"#fff",borderColor:"#4f46e5"}}>{busy?"Saving…":"Create department"}</button>
      </form>
      <div><h3 style={{marginTop:0}}>Departments ({departments.length})</h3>{departments.map(d=><article key={d.id} style={{border:"1px solid #e8ecf3",borderRadius:10,padding:13,marginBottom:10}}><strong>{d.name}</strong><p style={{margin:"5px 0",fontSize:12,color:"#667085"}}>{d.description||"No description"}</p><p style={{margin:0,fontSize:12,color:"#667085"}}>Services: {d.skills||"Not assigned"}</p></article>)}</div>
    </div>}
  </section>;
}
