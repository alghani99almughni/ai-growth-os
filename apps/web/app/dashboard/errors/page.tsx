"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

const API = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Call = {
    id: string;
    customer_name: string;
    customer_phone: string;
    started_at: string;
    duration_seconds: number;
    turn_count: number;
    flag_count: number;
    severity: string | null;
    outcome: string | null;
    intent_final: string | null;
};

export default function ErrorsPage() {
    const [tenant, setTenant] = useState<any>(null);
    const [calls, setCalls] = useState<Call[]>([]);
    const [stats, setStats] = useState<any>(null);
    const [flags, setFlags] = useState<any[]>([]);
    const [filter, setFilter] = useState<string>("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    const token = () => localStorage.getItem("ago_access_token") || "";

    useEffect(() => {
        const raw = localStorage.getItem("ago_tenant");
        if (!raw) {
            location.href = "/login";
            return;
        }
        setTenant(JSON.parse(raw));
    }, []);

    useEffect(() => {
        if (!tenant) return;
        load();
    }, [tenant, filter]);

    async function load() {
        setBusy(true);
        setError("");
        try {
            const h = { Authorization: "Bearer " + token() };
            const url = API() + "/api/v1/calls/problems" +
                (filter ? "?severity=" + encodeURIComponent(filter) : "");
            const [callsRes, statsRes, flagsRes] = await Promise.all([
                fetch(url, { headers: h }),
                fetch(API() + "/api/v1/calls/stats/summary", { headers: h }),
                fetch(API() + "/api/v1/calls/stats/flags?limit=10", { headers: h }),
            ]);
            if (!callsRes.ok) throw new Error("Unable to load problem calls");
            const callsData = await callsRes.json();
            setCalls(callsData.calls || []);
            if (statsRes.ok) setStats(await statsRes.json());
            if (flagsRes.ok) setFlags((await flagsRes.json()).flags || []);
        } catch (e: any) {
            setError(e?.message || "Unable to load errors.");
        } finally {
            setBusy(false);
        }
    }

    if (!tenant) {
        return (
            <main className="shell">
                <div className="hero"><h1>Loading…</h1></div>
            </main>
        );
    }

    return (
        <main className="shell">
            <section className="hero">
                <p>AI GROWTH OS • QUALITY CONTROL</p>
                <h1>Errors &amp; QA</h1>
                <p>
                    Every captured call is auto-analyzed. Loops, stuck states,
                    slow turns and ignored cancellations are flagged here.
                </p>
            </section>

            <nav style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "18px 0" }}>
                <Link href="/dashboard" style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: "10px 14px", background: "#fff" }}>
                    ← Back to dashboard
                </Link>
            </nav>

            {error && <p style={{ color: "crimson" }}>{error}</p>}

            {stats && (
                <section className="grid" style={{ marginBottom: 24 }}>
                    <article className="card">
                        <small>Total calls</small>
                        <p style={{ fontSize: 32, margin: "6px 0" }}>{stats.total_calls}</p>
                        <small>captured</small>
                    </article>
                    <article className="card">
                        <small>Clean calls</small>
                        <p style={{ fontSize: 32, margin: "6px 0" }}>{stats.clean_calls}</p>
                        <small>{100 - (stats.error_rate_pct || 0)}% success rate</small>
                    </article>
                    <article className="card">
                        <small>Calls with flags</small>
                        <p style={{ fontSize: 32, margin: "6px 0" }}>{stats.calls_with_flags}</p>
                        <small>{stats.error_rate_pct || 0}% error rate</small>
                    </article>
                    <article className="card">
                        <small>Avg duration</small>
                        <p style={{ fontSize: 32, margin: "6px 0" }}>{stats.avg_duration_seconds}s</p>
                        <small>{stats.avg_turns_per_call} turns avg</small>
                    </article>
                </section>
            )}

            {flags.length > 0 && (
                <section className="card" style={{ marginBottom: 24 }}>
                    <h3 style={{ marginTop: 0 }}>Top issue types</h3>
                    <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
                        {flags.map((f) => (
                            <span
                                key={f.flag_type}
                                style={{
                                    background: "#f3f4f6",
                                    borderRadius: 999,
                                    padding: "6px 12px",
                                    fontSize: 13,
                                }}
                            >
                                {f.flag_type.replace(/_/g, " ")} • {f.count}
                            </span>
                        ))}
                    </div>
                </section>
            )}

            <section>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                    <h2 style={{ margin: 0 }}>Problem calls {busy ? "…" : `(${calls.length})`}</h2>
                    <div className="tabs" style={{ margin: 0 }}>
                        {["", "error", "warning", "info"].map((s) => (
                            <button
                                key={s || "all"}
                                onClick={() => setFilter(s)}
                                style={{
                                    background: filter === s ? "#111827" : "#fff",
                                    color: filter === s ? "#fff" : "#111827",
                                    border: "1px solid #e5e7eb",
                                }}
                            >
                                {s || "All"}
                            </button>
                        ))}
                    </div>
                </div>

                {calls.length === 0 && !busy && (
                    <div className="card">
                        <p>No problem calls found for this filter.</p>
                        <p style={{ opacity: 0.7, fontSize: 13 }}>
                            As calls come in, auto-detection will flag loops, stuck
                            states, and slow turns here.
                        </p>
                    </div>
                )}

                {calls.map((c) => (
                    <Link
                        key={c.id}
                        href={`/dashboard/errors/${c.id}`}
                        style={{ display: "block", marginBottom: 12 }}
                    >
                        <article className="card" style={{ cursor: "pointer" }}>
                            <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap" }}>
                                <div style={{ minWidth: 0 }}>
                                    <strong>
                                        {c.customer_name || "Guest"}
                                        {c.customer_phone && (
                                            <span style={{ opacity: 0.6, fontWeight: 400 }}>
                                                {" "}• {c.customer_phone}
                                            </span>
                                        )}
                                    </strong>
                                    <div style={{ fontSize: 13, opacity: 0.7, marginTop: 4 }}>
                                        {c.started_at ? new Date(c.started_at).toLocaleString() : "—"}
                                        {" • "}
                                        {c.duration_seconds}s
                                        {" • "}
                                        {c.turn_count} turns
                                        {c.intent_final && ` • ${c.intent_final}`}
                                    </div>
                                </div>
                                <div style={{ textAlign: "right", flexShrink: 0 }}>
                                    <span
                                        style={{
                                            background:
                                                c.severity === "error" ? "#fee2e2"
                                                    : c.severity === "warning" ? "#fef3c7"
                                                        : "#e0e7ff",
                                            color:
                                                c.severity === "error" ? "#991b1b"
                                                    : c.severity === "warning" ? "#92400e"
                                                        : "#3730a3",
                                            borderRadius: 999,
                                            padding: "4px 10px",
                                            fontSize: 12,
                                            fontWeight: 600,
                                        }}
                                    >
                                        {c.flag_count} flag{c.flag_count === 1 ? "" : "s"}
                                    </span>
                                    {c.outcome && (
                                        <div style={{ fontSize: 11, opacity: 0.6, marginTop: 6 }}>
                                            {c.outcome}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </article>
                    </Link>
                ))}
            </section>
        </main>
    );
}