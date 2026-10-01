"use client";
import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

const API = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Turn = {
    id: string;
    turn_number: number;
    ts_started: string | null;
    customer_text: string;
    customer_audio_url: string | null;
    ai_text: string;
    ai_audio_url: string | null;
    intent: string | null;
    confidence: number;
    language: string;
    source: string;
    handler_name: string | null;
    handler_succeeded: boolean;
    state_before: string | null;
    state_after: string | null;
    cleared_at_set: boolean;
    total_latency_ms: number;
    tokens_used: number;
    cost_usd: number;
    error: string | null;
};

type Flag = {
    id: string;
    flag_type: string;
    severity: string;
    message: string;
    turn_id: string | null;
    created_at: string;
};

type Recording = {
    id: string;
    customer_name: string;
    customer_phone: string;
    channel: string;
    started_at: string;
    ended_at: string;
    duration_seconds: number;
    turn_count: number;
    outcome: string | null;
    intent_final: string | null;
    has_flags: boolean;
    flag_count: number;
    severity: string | null;
    avg_turn_latency_ms: number;
};

export default function CallDetailPage() {
    const params = useParams<{ id: string }>();
    const router = useRouter();
    const recordingId = params?.id;

    const [recording, setRecording] = useState<Recording | null>(null);
    const [turns, setTurns] = useState<Turn[]>([]);
    const [flags, setFlags] = useState<Flag[]>([]);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    const token = () => localStorage.getItem("ago_access_token") || "";

    useEffect(() => {
        if (!recordingId) return;
        const raw = localStorage.getItem("ago_tenant");
        if (!raw) {
            location.href = "/login";
            return;
        }
        load();
    }, [recordingId]);

    async function load() {
        if (!recordingId) return;
        setBusy(true);
        setError("");
        try {
            const h = { Authorization: "Bearer " + token() };
            const r = await fetch(API() + "/api/v1/calls/" + recordingId, { headers: h });
            if (!r.ok) throw new Error("Unable to load call");
            const data = await r.json();
            setRecording(data.recording);
            setTurns(data.turns || []);
            setFlags(data.flags || []);
        } catch (e: any) {
            setError(e?.message || "Unable to load call details.");
        } finally {
            setBusy(false);
        }
    }

    function audioUrl(side: "customer" | "ai", turnNumber: number): string {
        return API() + "/api/v1/calls/" + recordingId + "/audio/" + side + "/" + turnNumber;
    }

    const flagsByTurn: Record<string, Flag[]> = {};
    for (const f of flags) {
        if (f.turn_id) {
            (flagsByTurn[f.turn_id] = flagsByTurn[f.turn_id] || []).push(f);
        }
    }

    if (!recording && !busy) {
        return (
            <main className="shell">
                <div className="hero"><h1>Loading…</h1></div>
                {error && <p style={{ color: "crimson", marginTop: 16 }}>{error}</p>}
            </main>
        );
    }

    return (
        <main className="shell">
            <section className="hero">
                <p>AI GROWTH OS • CALL DETAIL</p>
                <h1>{recording?.customer_name || "Guest"}</h1>
                <p>
                    {recording?.customer_phone || "no phone"} • {recording?.channel} •{" "}
                    {recording?.duration_seconds}s • {recording?.turn_count} turns
                </p>
            </section>

            <nav style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "18px 0" }}>
                <Link
                    href="/dashboard/errors"
                    style={{
                        border: "1px solid #e5e7eb",
                        borderRadius: 10,
                        padding: "10px 14px",
                        background: "#fff",
                    }}
                >
                    ← All errors
                </Link>
                <Link
                    href="/dashboard"
                    style={{
                        border: "1px solid #e5e7eb",
                        borderRadius: 10,
                        padding: "10px 14px",
                        background: "#fff",
                    }}
                >
                    Dashboard
                </Link>
            </nav>

            {error && <p style={{ color: "crimson" }}>{error}</p>}

            {recording && (
                <section className="grid" style={{ marginBottom: 24 }}>
                    <article className="card">
                        <small>Started</small>
                        <p style={{ margin: "6px 0" }}>
                            {recording.started_at
                                ? new Date(recording.started_at).toLocaleString()
                                : "—"}
                        </p>
                    </article>
                    <article className="card">
                        <small>Outcome</small>
                        <p style={{ margin: "6px 0" }}>{recording.outcome || "—"}</p>
                    </article>
                    <article className="card">
                        <small>Final intent</small>
                        <p style={{ margin: "6px 0" }}>{recording.intent_final || "—"}</p>
                    </article>
                    <article className="card">
                        <small>Avg latency</small>
                        <p style={{ margin: "6px 0" }}>{recording.avg_turn_latency_ms}ms</p>
                    </article>
                </section>
            )}

            {flags.length > 0 && (
                <section className="card" style={{ marginBottom: 24 }}>
                    <h3 style={{ marginTop: 0 }}>Auto-detected issues</h3>
                    {flags.map((f) => (
                        <div
                            key={f.id}
                            style={{
                                display: "flex",
                                gap: 12,
                                alignItems: "flex-start",
                                padding: "10px 0",
                                borderBottom: "1px solid #f3f4f6",
                            }}
                        >
                            <span
                                style={{
                                    background:
                                        f.severity === "error"
                                            ? "#fee2e2"
                                            : f.severity === "warning"
                                                ? "#fef3c7"
                                                : "#e0e7ff",
                                    color:
                                        f.severity === "error"
                                            ? "#991b1b"
                                            : f.severity === "warning"
                                                ? "#92400e"
                                                : "#3730a3",
                                    borderRadius: 999,
                                    padding: "3px 10px",
                                    fontSize: 11,
                                    fontWeight: 700,
                                    textTransform: "uppercase",
                                    flexShrink: 0,
                                }}
                            >
                                {f.severity}
                            </span>
                            <div style={{ minWidth: 0 }}>
                                <strong>{f.flag_type.replace(/_/g, " ")}</strong>
                                <div style={{ fontSize: 13, opacity: 0.75, marginTop: 4 }}>
                                    {f.message}
                                </div>
                            </div>
                        </div>
                    ))}
                </section>
            )}

            <section>
                <h2>Turns ({turns.length})</h2>
                {turns.length === 0 && <p>No turns recorded.</p>}
                {turns.map((t) => (
                    <article key={t.id} className="card" style={{ marginBottom: 12 }}>
                        <div
                            style={{
                                display: "flex",
                                justifyContent: "space-between",
                                gap: 12,
                                flexWrap: "wrap",
                                alignItems: "center",
                            }}
                        >
                            <strong>Turn {t.turn_number}</strong>
                            <div style={{ fontSize: 12, opacity: 0.7 }}>
                                {t.ts_started ? new Date(t.ts_started).toLocaleTimeString() : "—"}
                                {" • "}
                                {t.total_latency_ms}ms
                                {t.tokens_used > 0 && ` • ${t.tokens_used} tokens`}
                            </div>
                        </div>

                        {flagsByTurn[t.id] && (
                            <div style={{ marginTop: 8 }}>
                                {flagsByTurn[t.id].map((f) => (
                                    <span
                                        key={f.id}
                                        style={{
                                            background: "#fee2e2",
                                            color: "#991b1b",
                                            borderRadius: 999,
                                            padding: "2px 8px",
                                            fontSize: 11,
                                            fontWeight: 600,
                                            marginRight: 6,
                                        }}
                                    >
                                        🚩 {f.flag_type.replace(/_/g, " ")}
                                    </span>
                                ))}
                            </div>
                        )}

                        <div style={{ marginTop: 14 }}>
                            <div style={{ fontSize: 12, opacity: 0.55, marginBottom: 4 }}>
                                CUSTOMER
                            </div>
                            <div style={{ marginBottom: 8 }}>{t.customer_text || "—"}</div>
                            {t.customer_audio_url && (
                                <audio
                                    controls
                                    src={audioUrl("customer", t.turn_number)}
                                    style={{ width: "100%", maxWidth: 400 }}
                                />
                            )}
                        </div>

                        <div style={{ marginTop: 14 }}>
                            <div style={{ fontSize: 12, opacity: 0.55, marginBottom: 4 }}>
                                AI ({t.source}
                                {t.handler_name ? ` • ${t.handler_name}` : ""})
                            </div>
                            <div style={{ marginBottom: 8 }}>{t.ai_text || "—"}</div>
                            {t.ai_audio_url && (
                                <audio
                                    controls
                                    src={audioUrl("ai", t.turn_number)}
                                    style={{ width: "100%", maxWidth: 400 }}
                                />
                            )}
                        </div>

                        {(t.state_before || t.state_after) && (
                            <div
                                style={{
                                    marginTop: 14,
                                    display: "flex",
                                    gap: 12,
                                    fontSize: 12,
                                    opacity: 0.7,
                                    flexWrap: "wrap",
                                }}
                            >
                                <span>
                                    State: <b>{t.state_before || "—"}</b> → <b>{t.state_after || "—"}</b>
                                </span>
                                {t.cleared_at_set && <span>✓ cleared_at set</span>}
                                {t.intent && <span>Intent: {t.intent}</span>}
                                {t.confidence > 0 && (
                                    <span>Confidence: {Math.round(t.confidence * 100)}%</span>
                                )}
                            </div>
                        )}

                        {t.error && (
                            <div style={{ marginTop: 8, color: "#991b1b", fontSize: 13 }}>
                                Error: {t.error}
                            </div>
                        )}
                    </article>
                ))}
            </section>
        </main>
    );
}