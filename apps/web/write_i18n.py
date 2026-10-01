"""Write a minimal i18n helper for the platform console."""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
TARGET = HERE / "lib" / "i18n.ts"
TARGET.parent.mkdir(parents=True, exist_ok=True)

CONTENT = '''"use client";

// Minimal i18n for the platform console. English + Hindi.
// Usage:
//   const t = useTranslation();
//   t("nav.tenants")  // -> "Tenants" or "किरायेदार"
//
// Language is stored in localStorage as "ago_lang".

import { useEffect, useState } from "react";

export const LANGUAGES = [
  { code: "en", label: "English", native: "English" },
  { code: "hi", label: "Hindi", native: "हिंदी" },
];

type Dict = Record<string, string>;

const EN: Dict = {
  // Nav
  "nav.overview": "Platform overview",
  "nav.tenants": "Tenants",
  "nav.ai": "AI providers",
  "nav.features": "Feature defaults",
  "nav.tickets": "Tickets",
  "nav.messages": "Messages",
  "nav.calendar": "Calendar",
  "nav.audit": "Audit log",
  "nav.health": "Health",
  "nav.settings": "Settings",
  "nav.tenant.overview": "Overview",
  "nav.tenant.calls": "Live calls",
  "nav.tenant.qr": "QR codes",
  "nav.tenant.orders": "Orders",
  "nav.tenant.bookings": "Bookings",
  "nav.tenant.crm": "Customers",
  "nav.tenant.services": "Services",
  "nav.tenant.team": "Team",
  "nav.tenant.knowledge": "Business Brain",
  "nav.tenant.loyalty": "Loyalty",
  "nav.tenant.whatsapp": "WhatsApp",
  "nav.tenant.website": "Website",
  "nav.tenant.agent": "Voice agent",
  "nav.tenant.reviews": "Reviews",
  "nav.tenant.errors": "Call errors",
  "nav.tenant.support": "Support",
  "nav.tenant.settings": "Settings",

  // Common
  "action.save": "Save",
  "action.cancel": "Cancel",
  "action.delete": "Delete",
  "action.refresh": "Refresh",
  "action.open": "Open",
  "action.close": "Close",
  "action.back": "Back",
  "action.view_all": "View all",

  // Statuses
  "status.active": "Active",
  "status.suspended": "Suspended",
  "status.pending": "Pending",
  "status.closed": "Closed",
  "status.healthy": "Healthy",
  "status.watch": "Watch",
  "status.at_risk": "At risk",
  "status.critical": "Critical",

  // Overview
  "overview.title": "Platform Overview",
  "overview.subtitle": "Last 30 days across the entire platform.",
  "overview.total_tenants": "Total tenants",
  "overview.active_tenants": "Active tenants",
  "overview.customers": "Customers",
  "overview.leads": "Leads",
  "overview.orders": "Orders",
  "overview.ai_calls": "AI calls",
  "overview.signups": "Signups — last 30 days",
  "overview.recent_signups": "Recent signups",

  // Tenants
  "tenants.title": "Tenants",
  "tenants.search": "Search by name or slug…",
  "tenants.business": "Business",
  "tenants.industry": "Industry",
  "tenants.status": "Status",
  "tenants.health": "Health",
  "tenants.last_seen": "Last seen",
  "tenants.created": "Created",
  "tenants.actions": "Actions",
  "tenants.details": "Details",
  "tenants.open_site": "Open site",

  // Tickets
  "tickets.title": "Support Tickets",
  "tickets.open": "Open",
  "tickets.breached": "Breached SLA",
  "tickets.due_soon": "Due within 1h",
  "tickets.healthy": "Healthy",
  "tickets.subject": "Subject",
  "tickets.category": "Category",
  "tickets.priority": "Priority",
  "tickets.sla": "SLA",

  // Settings
  "settings.title": "Platform Settings",
  "settings.subtitle": "Global configuration for the whole platform.",
  "settings.company": "Company identity",
  "settings.sla": "SLA turnaround (hours)",
  "settings.alerts": "Alert channels",
  "settings.hours": "Business hours",
  "settings.toggles": "Platform toggles",
  "settings.save": "Save settings",

  // Auth
  "auth.sign_out": "Sign out",
  "auth.super_admin": "Super Admin",
  "auth.business_admin": "Business admin",
};

const HI: Dict = {
  // Nav
  "nav.overview": "प्लेटफ़ॉर्म अवलोकन",
  "nav.tenants": "किरायेदार",
  "nav.ai": "AI प्रदाता",
  "nav.features": "फ़ीचर डिफ़ॉल्ट",
  "nav.tickets": "टिकट",
  "nav.messages": "संदेश",
  "nav.calendar": "कैलेंडर",
  "nav.audit": "ऑडिट लॉग",
  "nav.health": "स्वास्थ्य",
  "nav.settings": "सेटिंग्स",
  "nav.tenant.overview": "अवलोकन",
  "nav.tenant.calls": "लाइव कॉल",
  "nav.tenant.qr": "QR कोड",
  "nav.tenant.orders": "ऑर्डर",
  "nav.tenant.bookings": "बुकिंग",
  "nav.tenant.crm": "ग्राहक",
  "nav.tenant.services": "सेवाएँ",
  "nav.tenant.team": "टीम",
  "nav.tenant.knowledge": "बिज़नेस ब्रेन",
  "nav.tenant.loyalty": "लॉयल्टी",
  "nav.tenant.whatsapp": "WhatsApp",
  "nav.tenant.website": "वेबसाइट",
  "nav.tenant.agent": "वॉइस एजेंट",
  "nav.tenant.reviews": "समीक्षाएँ",
  "nav.tenant.errors": "कॉल त्रुटियाँ",
  "nav.tenant.support": "सहायता",
  "nav.tenant.settings": "सेटिंग्स",

  // Common
  "action.save": "सहेजें",
  "action.cancel": "रद्द करें",
  "action.delete": "हटाएँ",
  "action.refresh": "रिफ़्रेश",
  "action.open": "खोलें",
  "action.close": "बंद करें",
  "action.back": "वापस",
  "action.view_all": "सभी देखें",

  // Statuses
  "status.active": "सक्रिय",
  "status.suspended": "निलंबित",
  "status.pending": "लंबित",
  "status.closed": "बंद",
  "status.healthy": "स्वस्थ",
  "status.watch": "निगरानी",
  "status.at_risk": "जोखिम में",
  "status.critical": "गंभीर",

  // Overview
  "overview.title": "प्लेटफ़ॉर्म अवलोकन",
  "overview.subtitle": "पिछले 30 दिनों का पूरा प्लेटफ़ॉर्म डेटा।",
  "overview.total_tenants": "कुल किरायेदार",
  "overview.active_tenants": "सक्रिय किरायेदार",
  "overview.customers": "ग्राहक",
  "overview.leads": "लीड",
  "overview.orders": "ऑर्डर",
  "overview.ai_calls": "AI कॉल",
  "overview.signups": "साइनअप — पिछले 30 दिन",
  "overview.recent_signups": "हाल के साइनअप",

  // Tenants
  "tenants.title": "किरायेदार",
  "tenants.search": "नाम या स्लग से खोजें…",
  "tenants.business": "व्यवसाय",
  "tenants.industry": "उद्योग",
  "tenants.status": "स्थिति",
  "tenants.health": "स्वास्थ्य",
  "tenants.last_seen": "अंतिम बार देखा",
  "tenants.created": "बनाया गया",
  "tenants.actions": "क्रियाएँ",
  "tenants.details": "विवरण",
  "tenants.open_site": "साइट खोलें",

  // Tickets
  "tickets.title": "सहायता टिकट",
  "tickets.open": "खुले",
  "tickets.breached": "SLA उल्लंघन",
  "tickets.due_soon": "1 घंटे में देय",
  "tickets.healthy": "स्वस्थ",
  "tickets.subject": "विषय",
  "tickets.category": "श्रेणी",
  "tickets.priority": "प्राथमिकता",
  "tickets.sla": "SLA",

  // Settings
  "settings.title": "प्लेटफ़ॉर्म सेटिंग्स",
  "settings.subtitle": "पूरे प्लेटफ़ॉर्म के लिए वैश्विक कॉन्फ़िगरेशन।",
  "settings.company": "कंपनी की पहचान",
  "settings.sla": "SLA समय (घंटे)",
  "settings.alerts": "अलर्ट चैनल",
  "settings.hours": "व्यावसायिक घंटे",
  "settings.toggles": "प्लेटफ़ॉर्म टॉगल",
  "settings.save": "सेटिंग्स सहेजें",

  // Auth
  "auth.sign_out": "साइन आउट",
  "auth.super_admin": "सुपर एडमिन",
  "auth.business_admin": "बिज़नेस एडमिन",
};

const DICTS: Record<string, Dict> = { en: EN, hi: HI };

export function getLang(): string {
  if (typeof window === "undefined") return "en";
  return localStorage.getItem("ago_lang") || "en";
}

export function setLang(code: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem("ago_lang", code);
  window.dispatchEvent(new Event("ago-lang-change"));
}

export function translate(key: string, lang?: string): string {
  const code = lang || getLang();
  const dict = DICTS[code] || EN;
  return dict[key] || EN[key] || key;
}

export function useTranslation() {
  const [lang, setLangState] = useState<string>("en");

  useEffect(() => {
    setLangState(getLang());
    const handler = () => setLangState(getLang());
    window.addEventListener("ago-lang-change", handler);
    return () => window.removeEventListener("ago-lang-change", handler);
  }, []);

  return {
    t: (key: string) => translate(key, lang),
    lang,
    setLang,
  };
}
'''

TARGET.write_text(CONTENT, encoding="utf-8")
print(f"File saved: {TARGET.stat().st_size} bytes")
print(f"Location: {TARGET}")