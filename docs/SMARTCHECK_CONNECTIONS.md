# SmartCheck Connections — implementation status

## Scope
This feature adds a platform-admin-only connection settings page for each selected tenant. The existing Google Apps Script / Google Sheets visitor workflow remains the source of truth; this change does not migrate data or modify the visitor flow.

## Status meanings
- `reachable`: the configured Apps Script URL returned HTTP 200 and JSON `status: "ok"` from `?action=HEALTH`.
- `unreachable`: the health request failed or did not return a valid response.
- `unverified`: HTTP 200 was received but the payload did not match the expected health contract.
- `link_saved_unverified`: a Drive folder URL was saved for reference only; this does not prove the platform can access it.
- `authenticated_sync_ready` remains false until a server-side bridge-secret handshake, legacy tenant-code mapping, and an authorized Drive read/write round-trip have been implemented and tested.

## Not yet production-ready
1. Configure the Apps Script bridge secret only in a server-side secret store; never expose it to the browser.
2. The connection center now stores an explicit legacy SmartCheck tenant-code mapping (for example, TNT-101) per AI Growth OS tenant and rejects duplicate mappings. Authenticated PING and actual visitor-data sync remain unimplemented.
3. Add authorized Google Drive OAuth access and verify read/write access to the chosen folder. A sharing URL is not an authorization grant.
4. Add tests for platform role enforcement, tenant isolation, bridge authentication, provider failure, and the Drive round-trip.
5. Run API and frontend checks, review the pull request, then deploy only after release approval.

No production environment variables or database settings are changed by this feature branch.


## Public QR registration scaffold
The tenant dashboard's fixed registration QR and the public `/visitor/{tenantSlug}` form are present in the branch, but deliberately fail closed. The QR/API requires `visitor_lifecycle_sync_ready=true` in the tenant's SmartCheck connection configuration. That flag must not be enabled until SmartCheck-backed list, approval/rejection, check-in/out, and QR verification are integrated and tested against the same data source. The current connection form does not expose this flag.
