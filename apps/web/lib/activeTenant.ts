export function getActiveTenantId(): string {
  if (typeof window === "undefined") return "";
  const urlTenant = new URLSearchParams(window.location.search).get("tenant");
  if (urlTenant) return urlTenant;
  try {
    const raw = localStorage.getItem("ago_tenant");
    const t = raw ? JSON.parse(raw) : null;
    return t?.id || "";
  } catch {
    return "";
  }
}