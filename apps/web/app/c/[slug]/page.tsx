"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import VoiceCallModal from "@/components/VoiceCallModal";

const API = () => String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

type Business = {
    id: string;
    name: string;
    slug: string;
    phone?: string;
    whatsapp_number?: string;
    address?: string;
    description?: string;
    industry?: string;
    agent_gender?: string;
    features?: Record<string, boolean>;
};

type Content = {
    eyebrow?: string;
    hero_title?: string;
    hero_emphasis?: string;
    hero_description?: string;
    about_title?: string;
    about_text?: string;
    whatsapp_number?: string;
    contact_heading?: string;
    contact_text?: string;
    quote?: string;
    hours_title?: string;
    hours_text?: string;
    grid_eyebrow?: string;
    grid_title?: string;
    grid_subtitle?: string;
    grid_cards?: { icon: string; title: string; body: string }[];
    hero_emoji_primary?: string;
    hero_emoji_secondary?: string;
    hero_badge_title?: string;
    hero_badge_subtitle?: string;
    trust_badges?: string[];
    theme?: string;
};

export default function TenantSite() {
    const params = useParams<{ slug: string }>();
    const slug = params?.slug || "";
    const [business, setBusiness] = useState<Business | null>(null);
    const [content, setContent] = useState<Content | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [callOpen, setCallOpen] = useState(false);

    useEffect(() => {
        if (!slug) return;
        (async () => {
            try {
                const r = await fetch(API() + "/api/v1/public/business/" + encodeURIComponent(slug) + "/website");
                if (!r.ok) throw new Error("Business not found");
                const data = await r.json();
                setBusiness(data.business);
                setContent(data.content || {});
            } catch (e: any) {
                setError(e?.message || "Unable to load site");
            } finally {
                setLoading(false);
            }
        })();
    }, [slug]);

    if (loading) {
        return <main className="shell"><section className="hero"><h1>Loading…</h1></section></main>;
    }
    if (error || !business) {
        return (
            <main className="shell">
                <section className="hero">
                    <h1>Site not found</h1>
                    <p>{error || "This business is not available."}</p>
                </section>
            </main>
        );
    }

    const c = content || {};
    const number = String(c.whatsapp_number || business.whatsapp_number || "").replace(/\D/g, "");
    const waMessage = encodeURIComponent("Hi " + business.name + ", I would like to know more.");
    const whatsappLink = number ? `https://wa.me/${number}?text=${waMessage}` : `https://wa.me/?text=${waMessage}`;
    const themeClass = "site-theme-" + (c.theme || "generic");

    const cards = c.grid_cards || [];
    const trust = c.trust_badges || [];

    return (
        <main className={"ss-page " + themeClass}>
            <header className="ss-nav">
                <a className="ss-brand" href="#top">
                    <span>{(business.name || "•").slice(0, 2).toUpperCase()}</span> {business.name}
                </a>
                <nav>
                    <a href="#about">About</a>
                    <a href="#offer">Explore</a>
                    <a href="#contact">Contact</a>
                </nav>
                <div className="ss-nav-actions">
                    <button type="button" className="ss-nav-cta ss-call-outline" onClick={() => setCallOpen(true)}>
                        ☎ Call us
                    </button>
                    {number && (
                        <a className="ss-nav-cta ss-nav-wa" href={whatsappLink} target="_blank" rel="noreferrer">
                            WhatsApp
                        </a>
                    )}
                </div>
            </header>

            <section id="top" className="ss-hero">
                <div className="ss-hero-copy">
                    {c.eyebrow && <p className="ss-eyebrow">{c.eyebrow}</p>}
                    <h1>
                        {c.hero_title || "Welcome."}
                        {c.hero_emphasis && <><br /><em>{c.hero_emphasis}</em></>}
                    </h1>
                    {c.hero_description && <p className="ss-lead">{c.hero_description}</p>}
                    <div className="ss-actions">
                        <button type="button" className="ss-primary ss-call-button" onClick={() => setCallOpen(true)}>
                            ☎ Call us <span>↗</span>
                        </button>
                        {number && (
                            <a className="ss-secondary" href={whatsappLink} target="_blank" rel="noreferrer">
                                WhatsApp us
                            </a>
                        )}
                        {cards.length > 0 && (
                            <a className="ss-secondary" href="#offer">Explore</a>
                        )}
                    </div>
                    {trust.length > 0 && (
                        <div className="ss-trust">
                            {trust.map((t, i) => <span key={i}>✓ {t.replace(/^✓\s*/, "")}</span>)}
                        </div>
                    )}
                </div>
                <div className="ss-hero-art" aria-label="Illustration">
                    <div className="ss-orbit ss-orbit-one" />
                    <div className="ss-orbit ss-orbit-two" />
                    <div className="ss-leaf ss-leaf-one">{c.hero_emoji_secondary || "🌿"}</div>
                    <div className="ss-leaf ss-leaf-two">{c.hero_emoji_secondary || "🍃"}</div>
                    <div className="ss-bowl">{c.hero_emoji_primary || "⭐"}</div>
                    {c.hero_badge_title && (
                        <div className="ss-art-card">
                            <strong>{c.hero_badge_title}</strong>
                            <span>{c.hero_badge_subtitle}</span>
                        </div>
                    )}
                </div>
            </section>

            {c.hours_text && (
                <section className="ss-hours" aria-label="Opening hours">
                    <p className="ss-eyebrow">VISIT US</p>
                    <h2>{c.hours_title || "Opening hours"}</h2>
                    <p>{c.hours_text}</p>
                </section>
            )}

            {(c.about_title || c.about_text) && (
                <section id="about" className="ss-section ss-intro">
                    <div>
                        <p className="ss-eyebrow">ABOUT</p>
                        <h2>{c.about_title}</h2>
                    </div>
                    <p>{c.about_text}</p>
                </section>
            )}

            {cards.length > 0 && (
                <section id="offer" className="ss-section">
                    <div className="ss-section-head">
                        <div>
                            <p className="ss-eyebrow">{c.grid_eyebrow || "EXPLORE"}</p>
                            <h2>{c.grid_title || "What we offer."}</h2>
                        </div>
                        {c.grid_subtitle && <p>{c.grid_subtitle}</p>}
                    </div>
                    <div className="ss-grid">
                        {cards.map((card, i) => (
                            <article key={i}>
                                <div className="ss-icon">{card.icon}</div>
                                <h3>{card.title}</h3>
                                <p>{card.body}</p>
                            </article>
                        ))}
                    </div>
                </section>
            )}

            {c.quote && (
                <section className="ss-quote">
                    <p>"{c.quote}"</p>
                    <span>— {business.name}</span>
                </section>
            )}

            <section id="contact" className="ss-contact">
                <div>
                    <p className="ss-eyebrow">CONTACT</p>
                    <h2>{c.contact_heading || "Let's talk."}</h2>
                    <p>{c.contact_text || ""}</p>
                </div>
                <div className="ss-contact-card">
                    {business.address && (
                        <div>
                            <span>📍</span>
                            <div>
                                <strong>Visit / connect</strong>
                                <p style={{ whiteSpace: "pre-line" }}>{business.address}</p>
                            </div>
                        </div>
                    )}
                    <div className="ss-contact-actions">
                        <button type="button" className="ss-wa ss-call-card" onClick={() => setCallOpen(true)}>
                            ☎ Call us <span>Talk now ↗</span>
                        </button>
                        {number && (
                            <a href={whatsappLink} target="_blank" rel="noreferrer" className="ss-wa">
                                💬 Continue on WhatsApp <span>↗</span>
                            </a>
                        )}
                    </div>
                </div>
            </section>

            <footer className="ss-footer">
                <strong>{business.name}</strong>
                {business.address && <span>{business.address.split("\n")[0]}</span>}
                <span>© {new Date().getFullYear()} {business.name}</span>
            </footer>

            {callOpen && (
                <VoiceCallModal
                    slug={slug}
                    businessName={business.name}
                    agentGender={business.agent_gender === "male" || business.agent_gender === "female" ? business.agent_gender : "female"}
                    onClose={() => setCallOpen(false)}
                />
            )}
        </main>
    );
}