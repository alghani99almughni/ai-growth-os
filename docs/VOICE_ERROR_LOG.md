# Voice Error Log

## 2026-09-23 — Voice regression: timing and booking confirmation

### Symptoms observed in live browser calls
- “may I know the timings” fell through to the generic unverified-answer / human-callback response instead of the deterministic business-hours response.
- “han may I know the timings” was also affected; browser STT may distort the transcript, so common timing intent must remain resilient.
- A booking for tomorrow at 2:00 PM reached the confirmation prompt, but “please confirm” fell through to the generic human-callback response instead of executing the confirmation path.

### Root cause
Recent edits introduced double-escaped regular-expression patterns in apps/api/app/brain.py. The affected patterns included whitespace/word-boundary matching used by intent routing and booking confirmation. This caused valid phrases to miss their deterministic routes and fall through to the last-resort AI/handoff path.

### Fix
Commit 1155482669ff9ecccb32c11a45461611cf430716 corrected the regex escaping in brain.py and added regression coverage for the observed timing and confirmation phrases.

### Prevention
The observed phrases are now explicit regression cases in apps/api/tests/test_voice_agent_regression.py so a future regex/routing change should fail CI before live browser testing.


## 2026-09-23 — Follow-up live test: STT timing and booking confirmation

### New symptoms
- "Man of the timings" still reached the generic unverified-answer response. This is a voice STT variant of a normal business-hours question and must remain deterministic.
- "Please confirm" reached the confirmation branch but the booking transaction returned the generic "couldn't complete" response.
- The 4:30 PM correction flow correctly recovered from an initial 4:30 AM interpretation, so date/time state merging is working.

### Engineering changes
- Timing intent is now checked before broad product wording and explicitly covers common STT timing fragments.
- Public voice booking confirmation now logs the exact transaction exception instead of hiding it.
- Repeated confirmation is idempotent when the same customer/service/start time already has a confirmed appointment.
- Appointment creation now rejects future/past times using the UTC-normalized value rather than comparing a tenant-local wall-clock value to UTC.
- Technical booking failures no longer automatically trigger a human callback; the caller receives a retryable confirmation message while the exact exception is logged for diagnosis.

### Required regression
Before the next live call, CI must pass and the API deploy containing these changes must be live.
