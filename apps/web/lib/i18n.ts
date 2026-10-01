// AI Growth OS — i18n strings (English + Hindi)
// One source of truth for all sidebar/platform/tenant labels.
// Keys are dotted namespaces: nav.*, page.*, action.*, status.*

export type Lang = "en" | "hi";

export const LANGUAGES: { code: Lang; name: string; native: string }[] = [
  { code: "en", name: "English", native: "English" },
  { code: "hi", name: "Hindi",   native: "हिंदी" },
];

const en: Record<string, string> = {
  // ── Platform nav ──
  "nav.platform": "Platform overview",
  "nav.tenants": "Tenants",
  "nav.ai": "AI providers",
  "nav.features": "Feature defaults",
  "nav.audit": "Audit log",
  "nav.health": "Health",
  "nav.monitoring": "Monitoring",
  "nav.settings": "Settings",
  "nav.tickets": "Tickets",
  "nav.messages": "Messages",
  "nav.calendar": "Calendar",

  // ── Tenant nav ──
  "nav.tenant.overview": "Overview",
  "nav.tenant.calls": "Live calls",
  "nav.tenant.qr": "QR codes",
  "nav.tenant.orders": "Orders",
  "nav.tenant.bookings": "Bookings",
  "nav.tenant.calendar": "Calendar",
  "nav.tenant.crm": "Customers",
  "nav.tenant.services": "Services",
  "nav.tenant.team": "Team",
  "nav.tenant.knowledge": "Business Brain",
  "nav.tenant.loyalty": "Loyalty",
  "nav.tenant.whatsapp": "WhatsApp",
  "nav.tenant.email": "Email",
  "nav.tenant.website": "Website",
  "nav.tenant.agent": "Voice agent",
  "nav.tenant.reviews": "Reviews",
  "nav.tenant.errors": "Call errors",
  "nav.tenant.support": "Support",
  "nav.tenant.settings": "Settings",
};

const hi: Record<string, string> = {
  // ── Platform nav ──
  "nav.platform": "प्लेटफ़ॉर्म अवलोकन",
  "nav.tenants": "किरायेदार",
  "nav.ai": "AI प्रदाता",
  "nav.features": "फ़ीचर डिफ़ॉल्ट",
  "nav.audit": "ऑडिट लॉग",
  "nav.health": "स्वास्थ्य",
  "nav.monitoring": "निगरानी",
  "nav.settings": "सेटिंग्स",
  "nav.tickets": "टिकट",
  "nav.messages": "संदेश",
  "nav.calendar": "कैलेंडर",

  // ── Tenant nav ──
  "nav.tenant.overview": "अवलोकन",
  "nav.tenant.calls": "लाइव कॉल",
  "nav.tenant.qr": "QR कोड",
  "nav.tenant.orders": "ऑर्डर",
  "nav.tenant.bookings": "बुकिंग",
  "nav.tenant.calendar": "कैलेंडर",
  "nav.tenant.crm": "ग्राहक",
  "nav.tenant.services": "सेवाएँ",
  "nav.tenant.team": "टीम",
  "nav.tenant.knowledge": "बिज़नेस ब्रेन",
  "nav.tenant.loyalty": "लॉयल्टी",
  "nav.tenant.whatsapp": "WhatsApp",
  "nav.tenant.email": "ईमेल",
  "nav.tenant.website": "वेबसाइट",
  "nav.tenant.agent": "वॉइस एजेंट",
  "nav.tenant.reviews": "समीक्षाएँ",
  "nav.tenant.errors": "कॉल त्रुटियाँ",
  "nav.tenant.support": "सहायता",
  "nav.tenant.settings": "सेटिंग्स",
};

const dicts: Record<Lang, Record<string, string>> = { en, hi };

let current: Lang = "en";

export function setLang(lang: string) {
  if (typeof window !== "undefined") {
    const next = (lang === "hi" ? "hi" : "en") as Lang;
    current = next;
    window.localStorage.setItem("ago_lang", next);
  }
}

export function getLang(): Lang {
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem("ago_lang");
    if (stored === "hi" || stored === "en") return stored;
  }
  return current;
}

export function t(key: string, vars?: Record<string, string>): string {
  const lang = getLang();
  const dict = dicts[lang] || dicts.en;
  let value = dict[key] ?? dicts.en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      value = value.replace(new RegExp("\\{" + k + "\\}", "g"), v);
    }
  }
  return value;
}

export function useTranslation() {
  return { t, lang: getLang(), setLang };
}