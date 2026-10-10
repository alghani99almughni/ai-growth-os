// apps/web/lib/activeTenant.ts

/**
 * Resolve the active tenant id.
 * Priority: ?tenant= in the URL → localStorage "ago_tenant" (JSON) → "".
 */
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

/**
 * Resolve the active auth token.
 * Matches what apps/web/app/login/page.tsx writes:
 *   localStorage.setItem("ago_access_token", data.access_token)
 */
export function getActiveToken(): string {
  if (typeof window === "undefined") return "";

  try {
    return localStorage.getItem("ago_access_token") || "";
  } catch {
    return "";
  }
}