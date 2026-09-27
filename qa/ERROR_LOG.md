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
