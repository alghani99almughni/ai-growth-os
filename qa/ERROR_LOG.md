# QA Error Log

## 2026-09-26 — Full 15-Tenant Matrix

### Failure: booking `now` caused HTTP 500
- Scope: all 15 QA tenants during the `today -> now` state-machine test.
- Root cause: `booking_reply_from_state()` called `available_slots()` without importing it in `brain.py`.
- Evidence: Render traceback reported `NameError: name 'available_slots' is not defined` at `apps/api/app/brain.py:426`.
- Solution: import `available_slots` from `.booking`; retain deterministic tenant-local next-slot resolution.
- Regression required: `today -> now`, `abhi`, `अभी`, no-slot-today recovery.

### Failure: natural booking confirmation was not accepted
- Scope: live booking create regression.
- Trigger: `Yes, confirm it`.
- Root cause: confirmation parser accepted short affirmative phrases but not natural affirmative + action phrases.
- Solution: accept bounded forms such as `yes, confirm it`, `sure please confirm`, and `okay book it` while keeping the confirmation deterministic.

### Performance observation
- 15-tenant concurrent voice-turn test reached approximately P50 5.10s / P95 8.40s on the failed run.
- No performance gate failure was recorded; booking correctness failures caused the run to fail.

## Release gate
This file records discovered defects and their solutions; a release is not marked production-ready until the complete automated matrix reports zero unresolved failures.

### Failure: live booking confirmation had no service configured
- Scope: SS Nutritions 50-scenario voice regression.
- Trigger: Monday -> 10 AM -> natural confirmation.
- Root cause: the production tenant had bookings enabled but no active Service row, so the transaction rejected the booking.
- Solution: create an explicit tenant-scoped `General Appointment` service on first confirmed booking when no active service exists; configured services remain preferred.

### Infrastructure test failure: transient Render health timeout
- Scope: QA/voice workflow deployment gate during overlapping Render deploys.
- Root cause: the workflow treated one 20-second health read timeout as a deployment failure.
- Solution: retry transient `requests` health errors with a bounded deployment window before failing the gate.

### Failure: `now` booking still returned HTTP 500 after the first fix
- Root cause: the new deterministic next-slot branch referenced `datetime` without importing it in `brain.py`.
- Evidence: Render reported `NameError: name 'datetime' is not defined` during `booking_reply_from_state()`.
- Solution: add the explicit `datetime` import and keep the full `today -> now -> next slot` regression mandatory.

### Failure: timezone name missing in next-slot calculation
- Root cause: the new `now` path referenced `ZoneInfo` at module scope without a global import; function-local imports elsewhere did not provide that symbol.
- Evidence: Render reported `NameError: name 'ZoneInfo' is not defined` for the 15-tenant `today -> now` tests.
- Solution: add a module-level `ZoneInfo` import and keep native/romanized `now` cases in the matrix.
