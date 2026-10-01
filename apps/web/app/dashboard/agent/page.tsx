"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

const API = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const LANGUAGES = [
    { code: "en", name: "English" },
    { code: "hi", name: "Hindi" },
    { code: "te", name: "Telugu" },
    { code: "ta", name: "Tamil" },
    { code: "kn", name: "Kannada" },
    { code: "ml", name: "Malayalam" },
    { code: "mr", name: "Marathi" },
    { code: "bn", name: "Bengali" },
    { code: "gu", name: "Gujarati" },
    { code: "pa", name: "Punjabi" },
    { code: "ur", name: "Urdu" },
];

const PREVIEW: Record<string, { female: string; male: string }> = {
    en: {
        female: "Hello, I'll have the team confirm that for you.",
        male: "Hello, I'll have the team confirm that for you.",
    },
    hi: {
        female: "नमस्ते, मैं टीम से पुष्टि करके आपको बताऊंगी।",
        male: "नमस्ते, मैं टीम से पुष्टि करके आपको बताऊंगा।",
    },
    te: {
        female: "నమస్కారం, నేను బృందంతో నిర్ధారించి మీకు తెలియజేస్తాను.",
        male: "నమస్కారం, నేను బృందంతో నిర్ధారించి మీకు తెలియజేస్తాను.",
    },
    ta: {
        female: "வணக்கம், நான் குழுவுடன் உறுதிசெய்து தெரிவிக்கிறேன்.",
        male: "வணக்கம், நான் குழுவுடன் உறுதிசெய்து தெரிவிக்கிறேன்.",
    },
    kn: {
        female: "ನಮಸ್ಕಾರ, ನಾನು ತಂಡದೊಂದಿಗೆ ಖಚಿತಪಡಿಸಿ ತಿಳಿಸುತ್ತೇನೆ.",
        male: "ನಮಸ್ಕಾರ, ನಾನು ತಂಡದೊಂದಿಗೆ ಖಚಿತಪಡಿಸಿ ತಿಳಿಸುತ್ತೇನೆ.",
    },
    ml: {
        female: "നമസ്കാരം, ഞാൻ ടീമുമായി സ്ഥിരീകരിച്ച് അറിയിക്കാം.",
        male: "നമസ്കാരം, ഞാൻ ടീമുമായി സ്ഥിരീകരിച്ച് അറിയിക്കാം.",
    },
    mr: {
        female: "नमस्कार, मी टीमशी पुष्टी करून सांगेन.",
        male: "नमस्कार, मी टीमशी पुष्टी करून सांगेन.",
    },
    bn: {
        female: "নমস্কার, আমি টিমের সাথে নিশ্চিত করে জানাব।",
        male: "নমস্কার, আমি টিমের সাথে নিশ্চিত করে জানাব।",
    },
    gu: {
        female: "નમસ્તે, હું ટીમ સાથે ખાતરી કરીને જણાવીશ.",
        male: "નમસ્તે, હું ટીમ સાથે ખાતરી કરીને જણાવીશ.",
    },
    pa: {
        female: "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਟੀਮ ਤੋਂ ਪੁਸ਼ਟੀ ਕਰਕੇ ਦੱਸ ਸਕਦੀ ਹਾਂ।",
        male: "ਸਤ ਸ੍ਰੀ ਅਕਾਲ, ਮੈਂ ਟੀਮ ਤੋਂ ਪੁਸ਼ਟੀ ਕਰਕੇ ਦੱਸ ਸਕਦਾ ਹਾਂ।",
    },
    ur: {
        female: "السلام علیکم، میں ٹیم سے تصدیق کر کے بتاؤں گی۔",
        male: "السلام علیکم، میں ٹیم سے تصدیق کر کے بتاؤں گا۔",
    },
};

export default function AgentVoicePage() {
    const [tenant, setTenant] = useState<any>(null);
    const [gender, setGender] = useState<"female" | "male">("female");
    const [agentName, setAgentName] = useState("");
    const [closingSoon, setClosingSoon] = useState<30 | 15 | 0>(30);
    const [previewLang, setPreviewLang] = useState("en");
    const [busy, setBusy] = useState(false);
    const [saved, setSaved] = useState(false);
    const [error, setError] = useState("");

    const token = () => localStorage.getItem("ago_access_token") || "";

    useEffect(() => {
        const raw = localStorage.getItem("ago_tenant");
        if (!raw) {
            location.href = "/login";
            return;
        }
        const t = JSON.parse(raw);
        setTenant(t);
        setGender((t.agent_gender as any) === "male" ? "male" : "female");
        setAgentName(t.agent_name || "");
        setClosingSoon(([0, 15, 30].includes(t.closing_soon_minutes) ? t.closing_soon_minutes : 30) as any);
    }, []);

    async function save() {
        if (!tenant) return;
        setBusy(true);
        setError("");
        try {
            const body = {
                agent_gender: gender,
                agent_name: agentName.trim() || undefined,
                closing_soon_minutes: closingSoon,
            };
            const r = await fetch(API() + "/api/v1/tenants/" + tenant.id + "/profile", {
                method: "PUT",
                headers: {
                    Authorization: "Bearer " + token(),
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(body),
            });
            if (!r.ok) {
                const x = await r.json().catch(() => ({}));
                throw new Error(x.detail || "Unable to save agent voice settings");
            }
            const updated = await r.json();
            setTenant(updated);
            localStorage.setItem("ago_tenant", JSON.stringify(updated));
            setSaved(true);
            setTimeout(() => setSaved(false), 2500);
        } catch (e: any) {
            setError(e?.message || "Save failed");
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

    const preview = PREVIEW[previewLang] || PREVIEW.en;
    const previewText = preview[gender];

    return (
        <main className="shell">
            <section className="hero">
                <p>AI GROWTH OS • AGENT IDENTITY</p>
                <h1>AI Receptionist</h1>
                <p>
                    Choose how your AI receptionist sounds and speaks.
                    Changes take effect on the next call.
                </p>
            </section>

            <nav style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "18px 0" }}>
                <Link
                    href="/dashboard"
                    style={{
                        border: "1px solid #e5e7eb",
                        borderRadius: 10,
                        padding: "10px 14px",
                        background: "#fff",
                    }}
                >
                    ← Dashboard
                </Link>
            </nav>

            {error && <p style={{ color: "crimson" }}>{error}</p>}

            <section className="card" style={{ marginBottom: 24 }}>
                <h2 style={{ marginTop: 0 }}>Gender</h2>
                <p style={{ opacity: 0.7, fontSize: 14, marginTop: 0 }}>
                    The AI uses gender-correct grammar in every language that
                    supports it (Hindi, Marathi, Punjabi, Urdu).
                </p>

                <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}>
                    {(["female", "male"] as const).map((g) => (
                        <button
                            key={g}
                            onClick={() => setGender(g)}
                            style={{
                                background: gender === g ? "#111827" : "#fff",
                                color: gender === g ? "#fff" : "#111827",
                                border: "2px solid #111827",
                                padding: "16px 24px",
                                borderRadius: 14,
                                fontSize: 15,
                                fontWeight: 600,
                                cursor: "pointer",
                                minWidth: 160,
                            }}
                        >
                            {g === "female" ? "👩  Female" : "👨  Male"}
                        </button>
                    ))}
                </div>
            </section>

            <section className="card" style={{ marginBottom: 24 }}>
                <h2 style={{ marginTop: 0 }}>Live preview</h2>
                <label style={{ display: "block", fontSize: 13, opacity: 0.7 }}>
                    Preview language
                </label>
                <select
                    value={previewLang}
                    onChange={(e) => setPreviewLang(e.target.value)}
                    style={{ maxWidth: 240 }}
                >
                    {LANGUAGES.map((l) => (
                        <option key={l.code} value={l.code}>{l.name}</option>
                    ))}
                </select>
                <div
                    style={{
                        marginTop: 12,
                        padding: 16,
                        background: "#f3f4f6",
                        borderRadius: 12,
                        fontSize: 16,
                        lineHeight: 1.5,
                    }}
                >
                    {previewText}
                </div>
                <p style={{ fontSize: 12, opacity: 0.6, marginTop: 8 }}>
                    {["hi", "mr", "pa", "ur"].includes(previewLang)
                        ? "This language shows a gender-based grammar change."
                        : "This language uses the same first-person form for both genders."}
                </p>
            </section>

            <section className="card" style={{ marginBottom: 24 }}>
                <h2 style={{ marginTop: 0 }}>Agent name (optional)</h2>
                <p style={{ opacity: 0.7, fontSize: 14, marginTop: 0 }}>
                    If set, the AI may introduce itself with this name.
                    Leave blank for the default "AI receptionist".
                </p>
                <input
                    type="text"
                    value={agentName}
                    onChange={(e) => setAgentName(e.target.value)}
                    placeholder="e.g. Neha, Arjun, Priya"
                    maxLength={40}
                    style={{ maxWidth: 320 }}
                />
            </section>

            <section className="card" style={{ marginBottom: 24 }}>
                <h2 style={{ marginTop: 0 }}>Closing-soon alert</h2>
                <p style={{ opacity: 0.7, fontSize: 14, marginTop: 0 }}>
                    When a customer calls just before your business closes, how
                    far ahead should the AI warn them?
                </p>
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 12 }}>
                    {([
                        { value: 30, label: "30 minutes before close" },
                        { value: 15, label: "15 minutes before close" },
                        { value: 0, label: "No warning" },
                    ] as const).map((opt) => (
                        <button
                            key={opt.value}
                            onClick={() => setClosingSoon(opt.value)}
                            style={{
                                background: closingSoon === opt.value ? "#111827" : "#fff",
                                color: closingSoon === opt.value ? "#fff" : "#111827",
                                border: "1px solid #111827",
                                padding: "10px 16px",
                                borderRadius: 10,
                                fontSize: 14,
                                cursor: "pointer",
                            }}
                        >
                            {opt.label}
                        </button>
                    ))}
                </div>
            </section>

            <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <button
                    onClick={save}
                    disabled={busy}
                    style={{
                        background: "#111827",
                        color: "#fff",
                        padding: "14px 28px",
                        borderRadius: 12,
                        fontSize: 15,
                        fontWeight: 600,
                    }}
                >
                    {busy ? "Saving…" : "Save settings"}
                </button>
                {saved && (
                    <span style={{ color: "#166534", fontWeight: 600 }}>
                        ✓ Saved. Next call will use the new settings.
                    </span>
                )}
            </div>
        </main>
    );
}