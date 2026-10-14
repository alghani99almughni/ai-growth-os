# SmartCheck / SnapSheet Google Sheets + Drive compatibility

This adapter is an **optional, tenant-scoped bridge**. AI Growth OS remains the source of truth for visitor approvals and gate events. It does not replace the existing SmartCheck Android app deployment.

## Setup

1. Create a separate Google Apps Script deployment for AI Growth OS. Do not overwrite the legacy SmartCheck deployment used by existing devices.
2. Add `apps/api/smartcheck_compat/Code.gs` to the new Apps Script project.
3. In **Project Settings → Script Properties**, set:
   - `AI_GROWTH_OS_API_KEY`: a random secret of at least 24 characters.
   - `SPREADSHEET_ID`: the spreadsheet ID to use.
   - `DRIVE_FOLDER_ID`: optional; otherwise the script creates/uses a `SmartCheckPasses` folder.
4. Authorize Spreadsheet and Drive access as the Google account that owns the sheet/folder, then deploy as a Web App. Copy the HTTPS URL shaped like `https://script.google.com/macros/s/DEPLOYMENT_ID/exec`.
5. In the tenant's Security & Visitors settings, configure that URL and the same API key. The API stores the key encrypted using a purpose-specific key derived from the server JWT secret; it never returns the secret in the config GET response.
6. Enable Security & Visitor Management for that tenant before using ping, sync, or migration endpoints.

## API operations

All routes are under `/api/v1/tenants/{tenant_id}/security` and require a valid AI Growth OS bearer token.

- `GET /smartcheck/config` — read URL and enabled state (returns only `has_shared_secret`, not the secret).
- `PUT /smartcheck/config` — configure the URL and key:
  ```json
  {"web_app_url":"https://script.google.com/macros/s/DEPLOYMENT_ID/exec","shared_secret":"replace-with-a-random-32-plus-character-secret","enabled":true}
  ```
- `POST /smartcheck/ping` — verifies the Apps Script can access its spreadsheet and Drive folder.
- `POST /passes/{pass_id}/smartcheck-sync` — mirrors one pass to the legacy sheet. Raw QR tokens are not exported; they are intentionally not stored by AI Growth OS.
- `POST /smartcheck/migrate-pending` — imports up to 500 pending records exported from the legacy spreadsheet as JSON. Example:
  ```json
  {"tickets":[{"ticket_id":"GP-100","tenant_id":"TENANT_ID","visitor_name":"Guest","visitor_mobile":"9876543210","purpose":"Meeting","target_destination":"Office","vehicle_number":"","industry":"apartment","status":"PENDING_APPROVAL"}]}
  ```

## Migration safeguards

- Every imported row is checked against the selected tenant; cross-tenant rows are rejected.
- Only pending approval rows are imported. Approved, rejected, checked-in, checked-out, cancelled, and expired rows are reported for manual reconciliation instead of being silently re-admitted.
- The imported pass ID is deterministic per tenant + legacy ticket ID, so rerunning the same migration skips duplicates.
- Every imported pass is created as **pending** and must receive fresh human approval in AI Growth OS.
- New QR tokens are generated for imported passes; only the authorized migration response returns them.
- The bridge validates that the endpoint is an HTTPS Google Apps Script deployment URL, and the script checks the shared API key before reading/writing data.

## Important limitations

- The current API supports controlled JSON migration; it does not directly authenticate to Google Drive or read a spreadsheet by ID. Export the legacy sheet to JSON/CSV and map the columns to the documented request before importing.
- AI Growth OS remains authoritative. A successful sheet sync is a mirror/audit copy, not proof that a visitor was approved or admitted.
- Verify the new Apps Script deployment with a test tenant and non-production rows before migrating live visitor data.
