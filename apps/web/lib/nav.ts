// The ONLY file you edit to change the sidebar.
// Add a line to add a menu item. Remove a line to remove one.
// Icon names come from lucide-react: https://lucide.dev/icons

export type NavItem = {
  href: string;
  label: string;
  icon: string;
  exact?: boolean;
  labelKey?: string;
};

export const TENANT_NAV: NavItem[] = [
  { href: "/dashboard",           label: "Overview",             icon: "LayoutDashboard", exact: true, labelKey: "nav.tenant.overview" },
  { href: "/dashboard/calls",     label: "Calls & Transcripts",   icon: "Phone" },
  { href: "/dashboard/qr",        label: "QR codes",              icon: "QrCode", labelKey: "nav.tenant.qr" },
  { href: "/dashboard/orders",    label: "Orders",                icon: "ClipboardList", labelKey: "nav.tenant.orders" },
  { href: "/dashboard/bookings",  label: "Bookings",              icon: "CalendarDays", labelKey: "nav.tenant.bookings" },
  { href: "/dashboard/business-hours", label: "Business hours",  icon: "CalendarDays" },
  { href: "/dashboard/calendar",  label: "Calendar",              icon: "CalendarDays", labelKey: "nav.tenant.calendar" },
  { href: "/dashboard/crm",       label: "Customers",             icon: "Users", labelKey: "nav.tenant.crm" },
  { href: "/dashboard/services",   label: "Services",             icon: "ShoppingBag", labelKey: "nav.tenant.services" },
  { href: "/dashboard/team",       label: "Team",                 icon: "UserCog", labelKey: "nav.tenant.team" },
  { href: "/dashboard/knowledge",  label: "Business Brain",       icon: "Brain", labelKey: "nav.tenant.knowledge" },
  { href: "/dashboard/loyalty",    label: "Loyalty",              icon: "Gift", labelKey: "nav.tenant.loyalty" },
  { href: "/dashboard/whatsapp",   label: "WhatsApp",             icon: "MessageCircle", labelKey: "nav.tenant.whatsapp" },
  { href: "/dashboard/email",      label: "Email",                icon: "Mail" },
  { href: "/dashboard/website",    label: "Website",              icon: "Globe", labelKey: "nav.tenant.website" },
  { href: "/dashboard/agent",      label: "Voice agent",           icon: "Bot", labelKey: "nav.tenant.agent" },
  { href: "/dashboard/errors",     label: "Call errors",           icon: "AlertTriangle", labelKey: "nav.tenant.errors" },
  { href: "/dashboard/support",    label: "Support",               icon: "LifeBuoy", labelKey: "nav.tenant.support" },
];

export const ADMIN_NAV: NavItem[] = [
  { href: "/platform",              label: "Platform overview", icon: "LayoutDashboard", exact: true, labelKey: "nav.overview" },
  { href: "/platform/tenants",      label: "Tenants",           icon: "Building2", labelKey: "nav.tenants" },
  { href: "/platform/tenants/new",  label: "Create tenant",     icon: "Building2" },
  { href: "/platform/integrations", label: "Tenant integrations", icon: "Settings2" },
  { href: "/platform/ai",           label: "AI providers",       icon: "Bot", labelKey: "nav.ai" },
  { href: "/platform/features",     label: "Feature defaults",   icon: "ToggleLeft", labelKey: "nav.features" },
  { href: "/platform/audit",        label: "Audit log",          icon: "FileText", labelKey: "nav.audit" },
  { href: "/platform/health",       label: "Health",             icon: "Activity", labelKey: "nav.health" },
  { href: "/platform/monitoring",   label: "Monitoring",         icon: "Activity" },
  { href: "/platform/settings",    label: "Settings",            icon: "Settings2", labelKey: "nav.settings" },
  { href: "/platform/tickets",     label: "Tickets",              icon: "LifeBuoy", labelKey: "nav.tickets" },
  { href: "/platform/messages",    label: "Messages",             icon: "MessageSquare", labelKey: "nav.messages" },
  { href: "/platform/calendar",    label: "Calendar",              icon: "CalendarDays", labelKey: "nav.calendar" },
];
