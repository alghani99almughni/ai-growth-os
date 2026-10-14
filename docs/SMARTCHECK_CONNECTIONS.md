# SmartCheck Connections — implementation status

## Scope
This feature adds a platform-admin-only connection settings page for each selected tenant. The existing Google Apps Script / Google Sheets visitor workflow remains the source of truth; this change does not migrate data or modify the visitor flow.

## Status meanings
- `reachable`: the configured Apps Script URL returned HTTP 200 and JSON `status: "ok"` from `?action=HEALTH`.
- `unreachable`: the health request failed or did not return a valid response.
- `unverified`: HTTP 200 was received but the payload did not match the expected health contract.
- `link_saved_unverified`: a Drive folder URL was saved for reference only; this does not prove the platform can access it.
- `authenticated_sync_ready` remains false until a server-side bridge-secret handshake, legacy tenant-code mapping, and an authorized Drive read/write round-trip have been implemented and tested.

## Deployment and verification requirements
1. Configure the same long random `AI_GROWTH_OS_BRIDGE_SECRET` in the Apps Script project properties and the API's server-side secret store. Never expose it to the browser.
2. Deploy the updated `integrations/SmartCheck/SmartCheck_Hardened_Apps_Script.gs` source as a new Apps Script web-app version. The update adds secure QR-token issuance on approval, the authenticated `VERIFY_TOKEN` action, and explicit cancellation.
3. In Super Admin → Security Connections, save the URL and exact legacy tenant code, then run **Verify & Enable Visitor Sync**. The server probes authenticated `PING`, `LIST_VISITORS`, and `VERIFY_TOKEN`; it only sets the lifecycle-ready flag if each contract responds correctly. A stale deployment fails closed.
4. Google Drive folder authorization is still separate and unverified. A sharing URL is not an authorization grant.
5. Run API and frontend checks, review the pull request, and perform a real end-to-end test against a test tenant before any release approval.

No production environment variables or database settings are changed by this feature branch.


## Public QR registration scaffold
The tenant dashboard's fixed registration QR and the public `/visitor/{tenantSlug}` form are present in the branch, but deliberately fail closed. The QR/API requires `visitor_lifecycle_sync_ready=true` in the tenant's SmartCheck connection configuration. That flag must not be enabled until SmartCheck-backed list, approval/rejection, check-in/out, and QR verification are integrated and tested against the same data source. The current connection form does not expose this flag.
