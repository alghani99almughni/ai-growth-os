import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "SS Nutritions | Natural Wellness & Healthy Living",
  description: "SS Nutritions helps families around Moinabad build healthier everyday habits through a practical, organic-focused wellness approach.",
};

const whatsappMessage = encodeURIComponent("Hi SS Nutritions, I would like to know more about your wellness programs.");
const whatsappLink = "https://wa.me/?text=" + whatsappMessage;

export default function SSNutritions() {
  return (
    <main className="ss-page">
      <header className="ss-nav">
        <a className="ss-brand" href="#top"><span>SS</span> Nutritions</a>
        <nav><a href="#about">About</a><a href="#wellness">Wellness</a><a href="#contact">Contact</a></nav>
        <a className="ss-nav-cta" href={whatsappLink} target="_blank" rel="noreferrer">WhatsApp</a>
      </header>

      <section id="top" className="ss-hero">
        <div className="ss-hero-copy">
          <p className="ss-eyebrow">MOINABAD · RANGAREDDY · TELANGANA</p>
          <h1>Feel better.<br/><em>Live consciously.</em></h1>
          <p className="ss-lead">Practical wellness for modern life, with an organic-focused approach to healthier everyday choices.</p>
          <div className="ss-actions">
            <a className="ss-primary" href={whatsappLink} target="_blank" rel="noreferrer">Start a conversation <span>↗</span></a>
            <a className="ss-secondary" href="#wellness">Explore wellness</a>
          </div>
          <div className="ss-trust"><span>✓ Personal guidance</span><span>✓ Everyday wellness</span><span>✓ Organic-focused</span></div>
        </div>
        <div className="ss-hero-art" aria-label="Natural wellness illustration">
          <div className="ss-orbit ss-orbit-one"/><div className="ss-orbit ss-orbit-two"/>
          <div className="ss-leaf ss-leaf-one">🌿</div><div className="ss-leaf ss-leaf-two">🍃</div>
          <div className="ss-bowl">🥗</div>
          <div className="ss-art-card"><strong>Small choices.</strong><span>Better everyday habits.</span></div>
        </div>
      </section>

      <section id="about" className="ss-section ss-intro">
        <div><p className="ss-eyebrow">OUR APPROACH</p><h2>Health consciousness starts with what you do every day.</h2></div>
        <p>SS Nutritions is a local wellness brand based in Moinabad, focused on helping people make informed, sustainable lifestyle choices. We keep the approach practical, personal and rooted in everyday habits.</p>
      </section>

      <section id="wellness" className="ss-section">
        <div className="ss-section-head"><div><p className="ss-eyebrow">WELLNESS AT SS</p><h2>A simpler way to work on your wellbeing.</h2></div><p>Explore the areas where we can support your journey.</p></div>
        <div className="ss-grid">
          <article><div className="ss-icon">🥗</div><h3>Nutrition guidance</h3><p>Understand everyday food choices and build practical routines around your goals.</p></article>
          <article><div className="ss-icon">🌱</div><h3>Organic-focused living</h3><p>Discover mindful ways to bring more natural, thoughtful choices into daily life.</p></article>
          <article><div className="ss-icon">🧘</div><h3>Healthy habits</h3><p>Turn small, consistent lifestyle decisions into routines you can actually maintain.</p></article>
          <article><div className="ss-icon">🤝</div><h3>Personal support</h3><p>Have a conversation about your needs and find an approach that fits your lifestyle.</p></article>
        </div>
      </section>

      <section className="ss-quote"><p>“Wellness is not about changing everything overnight. It is about making better choices, consistently.”</p><span>— SS Nutritions</span></section>

      <section id="contact" className="ss-contact">
        <div><p className="ss-eyebrow">LET'S TALK</p><h2>Your wellness journey can start with one conversation.</h2><p>Tell us what you are looking for and our team can guide you on the next step.</p></div>
        <div className="ss-contact-card">
          <div><span>📍</span><div><strong>Visit / connect</strong><p>Moinabad, Rangareddy District<br/>Telangana · 501504</p></div></div>
          <a href={whatsappLink} target="_blank" rel="noreferrer" className="ss-wa">💬 Continue on WhatsApp <span>↗</span></a>
          <p className="ss-note">For personalized nutrition or wellness concerns, consult an appropriately qualified healthcare professional.</p>
        </div>
      </section>

      <footer className="ss-footer"><strong>SS Nutritions</strong><span>Moinabad · Rangareddy · 501504</span><span>© 2026 SS Nutritions</span></footer>
    </main>
  );
}
