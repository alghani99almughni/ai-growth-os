"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

const API = String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
type CatalogEntry = { id: string; category: string; business_type: string; roles: string[]; is_active: boolean; sort_order: number };
const STARTER_TEMPLATES = [
  { key: "restaurant", label: "Restaurant / Cafe" }, { key: "hotel", label: "Hotel" },
  { key: "salon", label: "Salon / Beauty" }, { key: "dental", label: "Dental Clinic" },
  { key: "gym", label: "Gym / Fitness" }, { key: "health", label: "Health / Clinic" },
  { key: "wellness", label: "Wellness" }, { key: "real-estate", label: "Real Estate" },
  { key: "education", label: "Education" },
];
export default function NewTenantPage() {
  const router = useRouter();
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [category, setCategory] = useState("");
  const [catalogEntryId, setCatalogEntryId] = useState("");
  const [industry, setIndustry] = useState("wellness");
  const [businessName, setBusinessName] = useState("");
  const [ownerName, setOwnerName] = useState("");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [ownerPassword, setOwnerPassword] = useState("");
  const [contactNumber, setContactNumber] = useState("");
  const [whatsappNumber, setWhatsappNumber] = useState("");
  const [website, setWebsite] = useState("");
  const [address, setAddress] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [catalogLoading, setCatalogLoading] = useState(true);

  useEffect(() => {
    fetch(API + "/api/v1/public/industry-catalog", { cache: "no-store" })
      .then(async r => { if (!r.ok) throw new Error("Catalogue could not load (HTTP " + r.status + ")"); return r.json(); })
      .then(x => {
        const entries: CatalogEntry[] = (x.items || []).filter((v: CatalogEntry) => v.is_active);
        setCatalog(entries);
        const firstCategory = entries[0]?.category || "";
        setCategory(firstCategory);
        setCatalogEntryId(entries[0]?.id || "");
      })
      .catch(e => setErr(e.message || "Could not load active industry categories."))
      .finally(() => setCatalogLoading(false));
  }, []);

  const categories = useMemo(() => Array.from(new Set(catalog.filter(x => x.is_active).map(x => x.category))), [catalog]);
  const subcategories = useMemo(() => catalog.filter(x => x.is_active && x.category === category).sort((a,b) => a.sort_order-b.sort_order || a.business_type.localeCompare(b.business_type)), [catalog, category]);

  function changeCategory(value: string) {
    setCategory(value);
    setCatalogEntryId(catalog.find(x => x.is_active && x.category === value)?.id || "");
  }

  const submit = async () => {
    setErr("");
    if (!businessName.trim()) return setErr("Business name is required.");
    if (!catalogEntryId) return setErr("Choose an active industry category and business type.");
    if (!ownerName.trim() || !ownerEmail.trim() || ownerPassword.length < 8) return setErr("Owner name, email, and password (8+ chars) are required.");
    if (!contactNumber.trim()) return setErr("Contact number is required.");
    if (!whatsappNumber.trim()) return setErr("WhatsApp number is required.");
    setBusy(true);
    try {
      const token = localStorage.getItem("ago_access_token") || "";
      const res = await fetch(API + "/api/v1/platform/tenants/provision", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({
          business_name: businessName.trim(), slug: null, industry, owner_name: ownerName.trim(),
          owner_email: ownerEmail.trim(), owner_password: ownerPassword, phone: contactNumber.trim(),
          whatsapp_number: whatsappNumber.trim(), address: address.trim() || null, website: website.trim() || null,
          template: industry, business_hours: null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Unable to create tenant.");
      const tenantId = data.tenant?.id || data.tenant_id;
      if (!tenantId) throw new Error("Tenant was created but the API did not return its ID.");
      const selection = await fetch(API + "/api/v1/tenants/" + encodeURIComponent(tenantId) + "/industry-selection", {
        method: "PUT", headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({ catalog_entry_id: catalogEntryId, notes: null }),
      });
      const selected = await selection.json().catch(() => ({}));
      if (!selection.ok) throw new Error("Tenant was created, but industry selection was not saved: " + (selected.detail || selection.status));
      router.push("/platform/tenants/" + tenantId);
    } catch (e: any) { setErr(String(e?.message || "Unable to create tenant.")); setBusy(false); }
  };

  return <div style={{ maxWidth: 760, color: "#17213a" }}>
    <h1 style={{ margin: "0 0 6px" }}>Create Tenant</h1>
    <p style={{ color: "#75839a", marginTop: 0 }}>Select an active industry category and business type from the Super Admin catalogue. The selection is saved to the new tenant.</p>
    <section style={{ display: "grid", gap: 12, marginBottom: 20 }}>
      <Field label="Industry category">
        <select value={category} disabled={catalogLoading || categories.length===0} onChange={e=>changeCategory(e.target.value)} style={inp}>
          {categories.map(x=><option key={x} value={x}>{x}</option>)}
        </select>
      </Field>
      <Field label="Business type / subcategory">
        <select value={catalogEntryId} disabled={catalogLoading || subcategories.length===0} onChange={e=>setCatalogEntryId(e.target.value)} style={inp}>
          {subcategories.map(x=><option key={x.id} value={x.id}>{x.business_type}</option>)}
        </select>
        {catalogLoading && <small>Loading active catalogue…</small>}
        {!catalogLoading && categories.length===0 && <small>No active catalogue entries are available. Add one in Industry catalogue.</small>}
      </Field>
      <Field label="AI starter template">
        <select value={industry} onChange={e=>setIndustry(e.target.value)} style={inp}>{STARTER_TEMPLATES.map(x=><option key={x.key} value={x.key}>{x.label}</option>)}</select>
      </Field>
      <Field label="Business name"><input value={businessName} onChange={e=>setBusinessName(e.target.value)} placeholder="Business name" style={inp}/></Field>
      <hr style={rule}/>
      <Field label="Owner name"><input value={ownerName} onChange={e=>setOwnerName(e.target.value)} placeholder="Owner name" style={inp}/></Field>
      <Field label="Owner email (used to sign in)"><input type="email" value={ownerEmail} onChange={e=>setOwnerEmail(e.target.value)} placeholder="owner@example.com" style={inp}/></Field>
      <Field label="Owner password (8+ characters)"><input type="password" value={ownerPassword} onChange={e=>setOwnerPassword(e.target.value)} style={inp}/></Field>
      <hr style={rule}/>
      <Field label="Contact number"><input value={contactNumber} onChange={e=>setContactNumber(e.target.value)} placeholder="+91 98765 43210" style={inp}/></Field>
      <Field label="WhatsApp number"><input value={whatsappNumber} onChange={e=>setWhatsappNumber(e.target.value)} placeholder="+91 98765 43210" style={inp}/></Field>
      <Field label="Existing website (optional)"><input value={website} onChange={e=>setWebsite(e.target.value)} placeholder="https://theirbusiness.com" style={inp}/></Field>
      <Field label="Address (optional)"><textarea value={address} onChange={e=>setAddress(e.target.value)} rows={2} style={{...inp,fontFamily:"inherit"}}/></Field>
    </section>
    {err && <p role="alert" style={{ color: "#b6341f", marginBottom: 12 }}>{err}</p>}
    <button disabled={busy || catalogLoading || categories.length===0} onClick={submit} style={{ padding:"12px 24px", background:"#5b5cf0", color:"#fff", border:0, borderRadius:10, fontWeight:700, fontSize:14, cursor:busy?"wait":"pointer", opacity:busy?.7:1 }}>{busy ? "Creating…" : "Create Tenant"}</button>
  </div>;
}
function Field({label,children}:{label:string;children:React.ReactNode}) { return <label style={{display:"block"}}><span style={{display:"block",fontSize:11,color:"#8490a4",textTransform:"uppercase",letterSpacing:".06em",fontWeight:600,marginBottom:5}}>{label}</span>{children}</label>; }
const inp:React.CSSProperties={display:"block",width:"100%",padding:"11px 13px",border:"1px solid #d7dce5",borderRadius:9,fontSize:14,color:"#17213a",background:"#fff",outline:"none",boxSizing:"border-box"};
const rule:React.CSSProperties={border:0,borderTop:"1px solid #e8ecf3",margin:"6px 0"};
