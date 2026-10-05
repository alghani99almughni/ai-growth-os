"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

const api = () => String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type Customer = {
  id: string;
  name: string | null;
  phone: string;
  email: string | null;
  address: string | null;
  notes: string | null;
  tags: string | null;
  source: string | null;
  whatsapp_opt_in: boolean | null;
  portal_token: string | null;
};

type TimelineEvent = {
  id: string;
  call_id: string | null;
  channel: string;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type CallSummary = {
  customer_id: string;
  total_calls: number;
  total_duration_seconds: number;
  last_call_at: string | null;
  languages: string[];
  calls: Array<{
    id: string;
    call_number: number | null;
    created_at: string;
    duration_seconds: number | null;
    status: string;
    resolution: string | null;
    language: string | null;
    intent: string | null;
    summary: string | null;
    transcript: string | null;
  }>;
};

type LoyaltyInfo = { points: number; history: Array<{ id: string; points: number; reason: string; reference_id: string | null; created_at: string | null }> };

export default function CustomerDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = String(params?.id || "");

  const [tenantId, setTenantId] = useState("");
  const [token, setToken] = useState("");
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [calls, setCalls] = useState<CallSummary | null>(null);
  const [loyalty, setLoyalty] = useState<LoyaltyInfo | null>(null);

  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editAddress, setEditAddress] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [editTags, setEditTags] = useState("");

  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const urlTenant = typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("tenant") || ""
      : "";
    if (urlTenant) {
      setTenantId(urlTenant);
    } else {
      try {
        const raw = localStorage.getItem("ago_tenant");
        const t = raw ? JSON.parse(raw) : null;
        if (t?.id) setTenantId(t.id);
      } catch {}
    }
    setToken(localStorage.getItem("ago_access_token") || "");
  }, []);

  useEffect(() => {
    if (!tenantId || !token || !id) return;
    void load();
  }, [tenantId, token, id]);

  async function load() {
    setLoading(true); setErr(""); setOk("");
    const h = { Authorization: "Bearer " + token };
    const get = async (path: string) => {
      const r = await fetch(api() + path, { headers: h, cache: "no-store" });
      const raw = await r.text();
      let x: any = {};
      try { x = JSON.parse(raw); } catch {}
      if (!r.ok) throw new Error(x?.detail || "Request failed: " + path);
      return x;
    };
    try {
      const list = await get(`/api/v1/tenants/${tenantId}/customers`);
      const found = (list.items || []).find((c: any) => c.id === id);
      if (!found) throw new Error("Customer not found");
      setCustomer(found);
      setEditName(found.name || "");
      setEditEmail(found.email || "");
      setEditAddress(found.address || "");
      setEditNotes(found.notes || "");
      setEditTags(found.tags || "");

      const [tl, cs, loy] = await Promise.all([
        get(`/api/v1/tenants/${tenantId}/customers/${id}/interaction-timeline`).catch(() => ({ items: [] })),
        get(`/api/v1/tenants/${tenantId}/customers/${id}/call-summary`).catch(() => null),
        get(`/api/v1/tenants/${tenantId}/loyalty/${id}`).catch(() => null),
      ]);
      setTimeline(tl.items || []);
      setCalls(cs);
      setLoyalty(loy);
    } catch (e: any) {
      setErr(String(e?.message || "Unable to load customer"));
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    setBusy(true); setErr(""); setOk("");
    try {
      const r = await fetch(api() + `/api/v1/tenants/${tenantId}/customers/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
        body: JSON.stringify({
          name: editName,
          email: editEmail || null,
          address: editAddress || null,
          notes: editNotes || null,
          tags: editTags,
        }),
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Save failed");
      setCustomer(x);
      setOk("Saved");
    } catch (e: any) {
      setErr(String(e?.message || "Save failed"));
    } finally {
      setBusy(false);
    }
  }

  async function sharePwa() {
    setBusy(true); setErr(""); setOk("");
    try {
      const r = await fetch(api() + `/api/v1/tenants/${tenantId}/customers/${id}/share-pwa`, {
        method: "POST",
        headers: { Authorization: "Bearer " + token },
      });
      const x = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(x?.detail || "Share failed");
      setOk("Sent via WhatsApp");
    } catch (e: any) {
      setErr(String(e?.message || "Share failed"));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <div style={{ padding: 60, textAlign: "center", color: "#75839a" }}>Loading…</div>;
  if (!customer) return <div style={{ padding: 40, color: "#b00" }}>{err || "Customer not found"}</div>;

  const tags = (customer.tags || "").split(",").map((t) => t.trim()).filter(Boolean);

  return (
    <div style={{ maxWidth: 1000 }}>
      <button onClick={() => router.push("/dashboard/crm" + (tenantId ? `?tenant=${tenantId}` : ""))} style={{ background: "transparent", border: 0, color: "#5b5cf0", fontWeight: 600, cursor: "pointer", padding: 0, marginBottom: 12 }}>
        ← All customers
      </button>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>{customer.name || "Unnamed"}</h1>
          <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
            📞 {customer.phone}
            {customer.email ? <> · ✉️ {customer.email}</> : null}
            {customer.source ? <> · source: {customer.source}</> : null}
          </p>
          {tags.length > 0 && (
            <div style={{ marginTop: 8, display: "flex", gap: 6, flexWrap: "wrap" }}>
              {tags.map((t) => (
                <span key={t} style={{ background: "#f1ebff", color: "#6b4fbb", padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 700 }}>{t}</span>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <button onClick={sharePwa} disabled={busy} style={{ background: "#fff", border: "1px solid #d7dce5", color: "#17213a", padding: "10px 16px", borderRadius: 10, fontWeight: 600, cursor: "pointer", fontSize: 13 }}>
            Share PWA link
          </button>
          {customer.portal_token && (
            <a href={`/customer?business=&customer=${customer.portal_token}`} target="_blank" rel="noreferrer" style={{ background: "#fff", border: "1px solid #d7dce5", color: "#17213a", padding: "10px 16px", borderRadius: 10, fontWeight: 600, textDecoration: "none", fontSize: 13 }}>
              Open portal
            </a>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginTop: 24 }}>
        <Kpi label="Total calls" value={calls?.total_calls ?? 0} />
        <Kpi label="Call minutes" value={Math.round((calls?.total_duration_seconds ?? 0) / 60)} />
        <Kpi label="Loyalty points" value={loyalty?.points ?? 0} />
        <Kpi label="Interactions" value={timeline.length} />
      </div>

      <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginTop: 22 }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 15, color: "#17213a" }}>Contact details</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
          <Field label="Name"><input value={editName} onChange={(e) => setEditName(e.target.value)} style={input} /></Field>
          <Field label="Email"><input value={editEmail} onChange={(e) => setEditEmail(e.target.value)} style={input} /></Field>
          <Field label="Address"><input value={editAddress} onChange={(e) => setEditAddress(e.target.value)} style={input} /></Field>
          <Field label="Tags (comma separated)"><input value={editTags} onChange={(e) => setEditTags(e.target.value)} style={input} /></Field>
        </div>
        <Field label="Notes">
          <textarea value={editNotes} onChange={(e) => setEditNotes(e.target.value)} rows={3} style={{ ...input, fontFamily: "inherit" }} />
        </Field>
        <div style={{ marginTop: 14, display: "flex", gap: 12, alignItems: "center" }}>
          <button onClick={save} disabled={busy} style={{ background: "linear-gradient(135deg,#5b5cf0,#7159f7)", color: "#fff", border: 0, padding: "11px 22px", borderRadius: 10, fontWeight: 700, fontSize: 13, cursor: busy ? "wait" : "pointer" }}>
            {busy ? "Saving…" : "Save"}
          </button>
          {ok && <span style={{ color: "#1aa76c", fontSize: 13 }}>{ok}</span>}
          {err && <span style={{ color: "#b00", fontSize: 13 }}>{err}</span>}
        </div>
      </section>

      <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginTop: 22 }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 15, color: "#17213a" }}>Call history</h2>
        {!calls || calls.calls.length === 0 ? (
          <p style={{ color: "#98a2b4", fontSize: 13, margin: 0 }}>No calls yet.</p>
        ) : (
          <div>
            {calls.calls.slice(0, 20).map((c) => (
              <details key={c.id} style={{ borderTop: "1px solid #f1f4f8", padding: "10px 0" }}>
                <summary style={{ cursor: "pointer", fontSize: 13, color: "#17213a", fontWeight: 600 }}>
                  {new Date(c.created_at).toLocaleString()} · {c.status} · {c.intent || "-"} · {c.duration_seconds ?? 0}s
                </summary>
                <div style={{ marginTop: 8, fontSize: 12, color: "#4b5563" }}>
                  {c.summary && <p style={{ margin: "4px 0" }}><b>Summary:</b> {c.summary}</p>}
                  <div style={{ display: "flex", gap: 12, marginBottom: 6, flexWrap: "wrap" }}>
                    <span><b>Status:</b> {c.status}</span>
                    <span><b>Resolution:</b> {c.resolution || "-"}</span>
                    <span><b>Language:</b> {c.language || "-"}</span>
                  </div>
                  {c.transcript ? (
                    <pre style={{ margin: 0, padding: 12, background: "#f7f9fb", borderRadius: 8, whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 12, color: "#4b5563", maxHeight: 400, overflow: "auto" }}>
                      {c.transcript}
                    </pre>
                  ) : (
                    <p style={{ color: "#98a2b4", fontStyle: "italic" }}>No transcript recorded.</p>
                  )}
                </div>
              </details>
            ))}
          </div>
        )}
      </section>

      <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginTop: 22 }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 15, color: "#17213a" }}>Interaction timeline</h2>
        {timeline.length === 0 ? (
          <p style={{ color: "#98a2b4", fontSize: 13, margin: 0 }}>No interactions recorded.</p>
        ) : (
          <ol style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {timeline.map((e) => (
              <li key={e.id} style={{ padding: "10px 0", borderTop: "1px solid #f1f4f8" }}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                  <div>
                    <strong style={{ color: "#17213a", fontSize: 13 }}>{e.event_type}</strong>
                    <span style={{ color: "#75839a", fontSize: 12, marginLeft: 8 }}>via {e.channel}</span>
                  </div>
                  <span style={{ color: "#98a2b4", fontSize: 12 }}>{new Date(e.created_at).toLocaleString()}</span>
                </div>
                {Object.keys(e.payload || {}).length > 0 && (
                  <pre style={{ margin: "6px 0 0", fontSize: 11, color: "#5a7268", background: "#f7f9fb", padding: 10, borderRadius: 8, overflow: "auto" }}>
                    {JSON.stringify(e.payload, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ol>
        )}
      </section>

      <section style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 22, marginTop: 22 }}>
        <h2 style={{ margin: "0 0 12px", fontSize: 15, color: "#17213a" }}>Loyalty history</h2>
        {!loyalty || loyalty.history.length === 0 ? (
          <p style={{ color: "#98a2b4", fontSize: 13, margin: 0 }}>No loyalty activity.</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {loyalty.history.map((h) => (
              <li key={h.id} style={{ padding: "8px 0", borderTop: "1px solid #f1f4f8", display: "flex", justifyContent: "space-between" }}>
                <span>
                  <strong style={{ color: h.points >= 0 ? "#1aa76c" : "#b00" }}>{h.points >= 0 ? "+" : ""}{h.points}</strong>
                  <span style={{ color: "#75839a", marginLeft: 8 }}>{h.reason}</span>
                </span>
                <span style={{ color: "#98a2b4", fontSize: 12 }}>{h.created_at ? new Date(h.created_at).toLocaleString() : ""}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Kpi({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ background: "#fff", border: "1px solid #e8ecf3", borderRadius: 14, padding: 18 }}>
      <div style={{ fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: "#17213a", marginTop: 4 }}>{value}</div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "block", marginTop: 10 }}>
      <span style={{ display: "block", fontSize: 11, color: "#8490a4", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 600, marginBottom: 5 }}>{label}</span>
      {children}
    </label>
  );
}

const input: React.CSSProperties = {
  width: "100%", padding: "10px 12px", border: "1px solid #d7dce5", borderRadius: 8, fontSize: 13, color: "#17213a", background: "#fff", outline: "none", boxSizing: "border-box",
};