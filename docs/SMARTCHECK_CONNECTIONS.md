# SmartCheck Connections (feature branch)

## Scope
- Platform-admin-only connection settings, stored per tenant in `tenant_settings`.
- Server-side health check of a Google Apps Script Web App URL.
- Optional Google Drive folder URL storage.
- Existing visitor flows and tenant data are not migrated or modified by this connection setup.

## Status semantics
- `reachable` means only that `?action=HEALTH` returned a healthy response.
- A Drive folder URL is stored as `link_saved_unverified`; the URL does not grant Drive access.
- `authenticated_sync_ready` remains false until the bridge-secret handshake and a real read/write sync are implemented and verified. Do not present this as production-connected.

## Required follow-up before production
1. Configure the server-side Apps Script bridge secret without exposing it to the browser.
2. Implement and test authenticated `PING` / tenant mapping against the existing Apps Script.
3. Implement Google Drive authorization and a real sync round-trip.
4. Run focused API/UI tests, review the diff against latest `main`, and open a PR. Do not merge or deploy before review.
