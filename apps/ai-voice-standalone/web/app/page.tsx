const bars = [18,32,48,25,62,40,76,52,91,58,72,37,84,48,66,29,55,42,73,34,61,24,46,31,57,20,39,27,49,16,35,23,43,18,30];
const features = [
  ["◉","Natural voice conversations","Answer enquiries, explain services and guide customers through a consistent conversation."],
  ["⌁","Knowledge Brain","Use approved business information, service details, FAQs and industry templates—not invented facts."],
  ["▦","Appointments & callbacks","Capture customer details, handle booking requests and create callback handoffs."],
  ["◎","Human handoff","Escalate to configured staff, departments and availability when a person is needed."],
  ["文","Multilingual experience","Designed for multilingual customer conversations, including Indian-language workflows."],
  ["▤","CRM call history","Keep transcripts, call outcomes and customer context connected to the business workflow."]
];
export default function Home() {
  return <main>
    <header className="wrap nav">
      <a className="brand" href="#"><span className="logo">V</span> AI VOICE</a>
      <nav className="navlinks"><a href="#features">Platform</a><a href="#engine">Voice engines</a><a href="#plans">Plans</a></nav>
      <a className="navcta" href="mailto:contact@aigrowthos.com?subject=AI%20Voice%20Demo">Book a demo</a>
    </header>
    <section className="wrap hero">
      <div>
        <div className="eyebrow">AI voice receptionist for business</div>
        <h1>Your business.<br/><span>Always heard.</span></h1>
        <p className="lead">A voice-first customer engagement platform that answers questions, captures leads, supports bookings and brings your team into the conversation when needed.</p>
        <div className="actions"><a className="primary" href="mailto:contact@aigrowthos.com?subject=Start%20AI%20Voice">Get started <span aria-hidden="true"> ↗</span></a><a className="secondary" href="#engine">Explore voice engines</a></div>
        <p className="note">Start with the self-hosted Free AI engine. No paid AI inference tokens required for that option.</p>
      </div>
      <div className="visual" aria-label="Illustration of a live AI voice conversation">
        <div className="visualtop"><span>AI VOICE SESSION</span><span className="live">● LIVE EXPERIENCE</span></div>
        <div className="wave">{bars.map((h,i)=><i key={i} style={{"--h":h+"px"} as React.CSSProperties}/>)}</div>
        <div className="callrow"><span>Conversation status</span><strong>Ready to assist</strong></div>
        <div className="callrow"><span>Knowledge source</span><strong>Business-approved</strong></div>
        <div className="callrow"><span>Next step</span><strong>Human handoff available</strong></div>
      </div>
    </section>
    <section className="section" id="features"><div className="wrap">
      <div className="eyebrow">One voice workspace</div><h2>From first hello to the next action.</h2>
      <p className="sub">AI Voice is built around the real work that happens during a customer conversation—not just speech-to-text and a chatbot response.</p>
      <div className="grid">{features.map(([ico,title,desc])=><article className="tile" key={title}><div className="ico">{ico}</div><h3>{title}</h3><p>{desc}</p></article>)}</div>
    </div></section>
    <section className="section" id="engine"><div className="wrap">
      <div className="eyebrow">Choose your voice engine</div><h2>Two options for clients. Full control for platform admins.</h2>
      <p className="sub">Keep the Free and Paid choices simple for businesses. Platform administrators retain separate DID/SIP infrastructure controls.</p>
      <div className="plans">
        <article className="plan featured"><span className="tag">CLIENT OPTION · FREE</span><h3>Self-hosted AI engine</h3><p>Designed for zero-paid-AI-token inference using locally hosted components.</p><ul><li>Local speech recognition</li><li>Self-hosted language model</li><li>Local text-to-speech</li><li>Business Knowledge Brain</li><li>Usage depends on your hosting and hardware capacity</li></ul></article>
        <article className="plan"><span className="tag">CLIENT OPTION · PAID</span><h3>Managed AI providers</h3><p>Optional provider-backed voice models where a business needs a managed service or different performance profile.</p><ul><li>Provider options controlled by platform admin</li><li>Tenant-level access and usage limits</li><li>Centralized credentials and billing controls</li><li>Availability depends on configured providers</li></ul></article>
      </div>
      <p className="note">DID / SIP trunk and number provisioning are managed by Super Admin—not exposed as tenant infrastructure controls. Carrier, hosting and connectivity charges may still apply.</p>
    </div></section>
    <section className="section"><div className="wrap cta"><div><div className="eyebrow">Ready to hear the difference?</div><h2>Give every customer a clear next step.</h2><p className="sub">Talk to us about onboarding your business and configuring its voice knowledge.</p></div><a className="primary" href="mailto:contact@aigrowthos.com?subject=AI%20Voice%20Onboarding">Talk to our team ↗</a></div></section>
    <footer className="wrap footer"><strong>AI VOICE</strong><span>Independent voice product · Built for business conversations</span><span>© {new Date().getFullYear()} AI Voice</span></footer>
  </main>;
}