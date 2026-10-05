"use client";
import { useEffect, useMemo, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type CustomerInfo = {
  id: string | null;
  name: string;
  phone: string;
  email: string | null;
  whatsapp_opt_in: boolean;
  created_at: string | null;
};

type CallRecord = {
  id: string;
  customer_id: string | null;
  customer_name: string;
  customer_phone: string;
  customer_email: string | null;
  customer_whatsapp_opt_in: boolean;
  customer_created_at: string | null;
  source: string;
  status: string;
  department: string | null;
  staff_id: string | null;
  room_id: string | null;
  intent: string | null;
  summary: string | null;
  transcript: string | null;
  created_at: string;
};

const STATUS_COLOURS: Record<string, string> = {
  ringing: "badge-orange", ongoing: "badge-blue", in_progress: "badge-blue",
  completed: "badge-grey", resolved: "badge-grey", failed: "badge-grey",
  missed: "badge-grey", handoff_requested: "badge-orange", handoff_accepted: "badge-blue",
  handoff_unavailable: "badge-grey",
};

function fmtWhen(iso: string | null): string {
  if (!iso) return "—";
  try {
    const u = iso.endsWith("Z") ? iso : iso + "Z";
    return new Date(u).toLocaleString("en-IN", {
      day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: true,
    });
  } catch { return iso; }
}

function transcriptLines(raw: string | null): string[] {
  if (!raw) return [];
  return raw
    .replace(/\\\\n/g, "\n")
    .split(/\r?\n/)
    .map((x) => x.trim())
    .filter(Boolean)
    .reverse();
}

function esc(v: unknown): string {
  return String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export default function CallsPanel({ tenantId, token }: { tenantId: string; token: string }) {
  const [items, setItems] = useState<CallRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  const [openId, setOpenId] = useState("");
  const [exporting, setExporting] = useState(false);

  const authHeaders = () => ({ Authorization: "Bearer " + token });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll() {
    setLoading(true); setError("");
    try {
      const res = await jget(`/api/v1/tenants/${tenantId}/calls`);
      setItems(res.items || []);
    } catch (e: any) { setError(e.message || "Could not load calls"); }
    setLoading(false);
  }

  useEffect(() => { if (tenantId) void loadAll(); }, [tenantId]);

  const visible = useMemo(() => filter ? items.filter(c => {
    const f = filter.toLowerCase();
    return [c.status,c.intent,c.customer_name,c.customer_phone,c.summary,c.source].some(v => String(v || "").toLowerCase().includes(f));
  }) : items, [items, filter]);

  function exportExcel() {
    setExporting(true);
    const headers = ["Call time","Customer","Phone","Customer type","Email","WhatsApp opt-in","Source","Status","Intent","Department","Summary","Transcript"];
    const rows = visible.map(c => [
      fmtWhen(c.created_at), c.customer_name, c.customer_phone,
      c.customer_created_at && new Date(c.customer_created_at).getTime() <= new Date(c.created_at).getTime() ? "Existing customer" : "New customer",
      c.customer_email || "", c.customer_whatsapp_opt_in ? "Yes" : "No", c.source, c.status, c.intent || "",
      c.department || "", c.summary || "", transcriptLines(c.transcript).reverse().join("\n"),
    ]);
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
<Worksheet ss:Name="Calls"><Table>
<Row>${headers.map(h => `<Cell><Data ss:Type="String">${esc(h)}</Data></Cell>`).join("")}</Row>
${rows.map(row => `<Row>${row.map(v => `<Cell><Data ss:Type="String">${esc(v)}</Data></Cell>`).join("")}</Row>`).join("")}
</Table></Worksheet></Workbook>`;
    const blob = new Blob([xml], {type:"application/vnd.ms-excel"});
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `ai-growth-os-calls-${new Date().toISOString().slice(0,10)}.xls`; a.click();
    URL.revokeObjectURL(a.href); setExporting(false);
  }

  function shareEmail(c: CallRecord) {
    const subject = encodeURIComponent(`Call transcript — ${c.customer_name} — ${fmtWhen(c.created_at)}`);
    const body = encodeURIComponent([
      `Customer: ${c.customer_name}`, `Phone: ${c.customer_phone}`, `Call time: ${fmtWhen(c.created_at)}`,
      `Customer type: ${c.customer_created_at && new Date(c.customer_created_at).getTime() <= new Date(c.created_at).getTime() ? "Existing customer" : "New customer"}`,
      "", "Transcript:", transcriptLines(c.transcript).reverse().join("\n")
    ].join("\n"));
    window.location.href = `mailto:${encodeURIComponent(c.customer_email || "")}?subject=${subject}&body=${body}`;
  }

  function shareWhatsApp(c: CallRecord) {
    const text = encodeURIComponent([
      `Call transcript — ${c.customer_name}`, `Phone: ${c.customer_phone}`, `Call time: ${fmtWhen(c.created_at)}`, "",
      ...transcriptLines(c.transcript).reverse()
    ].join("\n"));
    window.open(`https://wa.me/?text=${text}`, "_blank", "noopener,noreferrer");
  }

  return (
    <section className="card">
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:12,flexWrap:"wrap"}}>
        <div>
          <h2 style={{margin:0}}>📞 Calls & Transcripts</h2>
          <p style={{margin:"4px 0 0",color:"#75839a",fontSize:13}}>{items.length} total call{items.length===1?"":"s"} · newest first</p>
        </div>
        <div style={{display:"flex",gap:8,alignItems:"center",flexWrap:"wrap"}}>
          <input placeholder="Search customer, phone, intent…" value={filter} onChange={e=>setFilter(e.target.value)}
            style={{padding:"8px 10px",border:"1px solid #d7dde8",borderRadius:8,fontSize:13,minWidth:240}} />
          <button className="btn-ghost" onClick={loadAll} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button>
          <button className="btn-primary" onClick={exportExcel} disabled={exporting || !visible.length}>{exporting ? "Exporting…" : "Export Excel"}</button>
        </div>
      </div>

      {error && <p style={{color:"#b00",marginTop:12}}>{error}</p>}

      <div style={{marginTop:20}}>
        {visible.length===0 && !loading && <div className="empty-state"><h3>{filter?"No matching calls":"No calls yet"}</h3><p>{filter?"Try clearing the search.":"Once the voice agent handles calls, they will appear here."}</p></div>}

        {visible.map(c => {
          const isOpen = openId === c.id;
          const existing = !!c.customer_created_at && new Date(c.customer_created_at).getTime() < new Date(c.created_at).getTime();
          const lines = transcriptLines(c.transcript);
          return (
            <article key={c.id} className="card" style={{marginBottom:14,padding:18,background:"#fff"}}>
              <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:16,flexWrap:"wrap"}}>
                <div style={{minWidth:280,flex:1}}>
                  <div style={{display:"flex",alignItems:"center",gap:8,flexWrap:"wrap"}}>
                    <strong style={{fontSize:16}}>{c.customer_name || "Customer"}</strong>
                    <span className={"badge "+(existing?"badge-blue":"badge-purple")}>{existing?"Existing customer":"New customer"}</span>
                    <span className={"badge "+(STATUS_COLOURS[c.status]||"badge-grey")}>{c.status}</span>
                    {c.intent && <span className="badge badge-purple">{c.intent}</span>}
                  </div>
                  <div style={{marginTop:9,display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:"5px 18px",fontSize:13,color:"#4a5875"}}>
                    <div><b>📱</b> {c.customer_phone || "—"}</div>
                    <div><b>🕒</b> {fmtWhen(c.created_at)}</div>
                    <div><b>📧</b> {c.customer_email || "No email"}</div>
                    <div><b>💬</b> {c.customer_whatsapp_opt_in ? "WhatsApp opt-in" : "WhatsApp not opted-in"}</div>
                  </div>
                  <div style={{marginTop:6,fontSize:12,color:"#75839a"}}>
                    {c.department || "General"}{c.source ? ` · ${c.source}` : ""}{c.summary ? ` · ${c.summary}` : ""}
                  </div>
                </div>
                <div style={{display:"flex",gap:7,flexWrap:"wrap"}}>
                  <button className="btn-ghost" onClick={()=>setOpenId(isOpen?"":c.id)}>{isOpen?"Hide":"View"} transcript</button>
                  <button className="btn-ghost" onClick={()=>shareEmail(c)}>Email</button>
                  <button className="btn-ghost" onClick={()=>shareWhatsApp(c)}>WhatsApp</button>
                </div>
              </div>

              {isOpen && (
                <div style={{marginTop:16,borderTop:"1px solid #e8ecf3",paddingTop:14}}>
                  <div style={{fontSize:12,fontWeight:700,color:"#75839a",marginBottom:8}}>FULL TRANSCRIPT · NEWEST MESSAGE FIRST</div>
                  <div style={{display:"grid",gap:7,maxHeight:480,overflowY:"auto"}}>
                    {lines.length ? lines.map((line,i) => {
                      const customer = /^CUSTOMER\s*:/i.test(line);
                      const ai = /^AI\s*:/i.test(line);
                      return <div key={i} style={{padding:"9px 11px",borderRadius:9,background:customer?"#f4f8ff":"#f6f8f6",border:"1px solid #e8ecf3",fontSize:13,lineHeight:1.5}}>
                        <strong>{customer?"CUSTOMER":ai?"AI":"SYSTEM"}</strong>
                        <span style={{marginLeft:8}}>{line.replace(/^(CUSTOMER|AI|SYSTEM)\s*:\s*/i,"")}</span>
                      </div>;
                    }) : <div style={{color:"#75839a"}}>No transcript captured for this call.</div>}
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
