# AI Voice Booking: 24/7, 12-Hour Clock, 365-Day and AM/PM Test Matrix

Status: PRELAUNCH REQUIREMENT — tests must pass before client onboarding.
Scope: `ai-voice` branch only. No Render deployment and no changes to `main`.

## Required behavior

1. Support 24/7 schedules and overnight opening windows.
2. Accept 12-hour spoken times and 24-hour numeric time input, resolving both to the tenant-local calendar time.
3. Correctly handle AM, PM, noon (12 PM), midnight (12 AM), minutes and spoken variants.
4. Support bookings across all weekdays and calendar dates, including month/year boundaries and leap day.
5. Use the tenant's configured IANA timezone for date resolution, opening hours, availability, storage and spoken confirmations.
6. The persisted call-start timestamp (CallRecord.started_at) is the authoritative reference for the tenant-local date, relative phrases and past-time checks; never use server wall time for a voice call.
7. Explicit AM/PM spoken by the customer always wins. Never rewrite an explicitly spoken AM to PM or PM to AM.
8. For a bare ambiguous time, evaluate both AM and PM against the requested date's configured tenant hours and the call-start timestamp. Resolve only if exactly one interpretation is within hours and still in the future; if both or neither qualify, ask AM/PM. For 24/7 businesses, ask AM/PM because both interpretations may be valid.
7. When AM/PM is genuinely ambiguous and both interpretations are plausible, ask the caller to clarify before availability is promised or a booking is created.
8. Check the actual tenant calendar before promising availability; re-check immediately before booking.
9. Persist bookings in the same tenant appointment database used by the dashboard; no parallel voice-only booking store.

## Call timestamp and interpretation tests

- Call starts at 4:45 PM tenant-local; customer says "today at 5:30"; reject the past AM interpretation and evaluate the 5:30 PM candidate.
- Call starts after business closing; "tomorrow at 10" must be interpreted using tomorrow's configured hours, not the call's current clock hour.
- Call starts in a different server timezone; relative date and past-slot filtering must still use the tenant-local call-start timestamp.
- Call timestamp is stored as UTC; verify the exact tenant-local timestamp used by date resolution, availability and rescheduling.
- Model suggests AM/PM but the customer transcript did not; the model suggestion must not count as explicit customer clarification.
- Rescheduling uses the same call-start reference and AM/PM rules as new bookings.
- If rescheduling requires AM/PM clarification, retain the pending date/time and accept a standalone "AM" or "PM" follow-up before reading back the new appointment.

## Mandatory AM/PM test cases

| Caller says | Expected local time | Expected behavior |
|---|---:|---|
| 9 AM | 09:00 | Morning slot only |
| 9 PM | 21:00 | Evening slot only |
| 12 AM | 00:00 | Midnight, correct calendar date |
| 12 PM | 12:00 | Noon |
| 12:30 AM | 00:30 | After midnight |
| 12:30 PM | 12:30 | Afternoon |
| 7:05 PM | 19:05 | Preserve minutes |
| 07:05 AM | 07:05 | Preserve leading zero / AM |
| 17:30 | 17:30 | Convert 24-hour input correctly |
| 00:15 | 00:15 | Midnight quarter past |
| 5:30 (ambiguous) | unresolved until context | Ask AM/PM unless configured hours/context makes one interpretation unambiguous |
| 5:30 AM explicitly | 05:30 | Never silently convert to PM |
| 5:30 PM explicitly | 17:30 | Never silently convert to AM |

## 24/7 and overnight schedule tests

- 00:00–23:59 daily: confirm availability at 00:00, 03:00, 12:00, 21:00 and 23:30 where service duration fits.
- 22:00–06:00 overnight: confirm late evening and after-midnight slots are both returned for the correct operating day.
- Search for 01:00 on Tuesday when Monday's 22:00–06:00 shift spans Tuesday morning.
- Ensure 06:00 closing boundary is excluded if the appointment would end after closing.
- Ensure appointments crossing midnight are handled consistently and do not create false conflicts.
- Confirm 24/7 is represented distinctly from a closed day and does not silently become 00:00–23:59 with a missing final interval.

## 365-day calendar tests

- All seven weekdays, including businesses configured open every day.
- Friday-to-Saturday, Saturday-to-Sunday, Sunday-to-Monday transitions.
- Month-end: 30th/31st to next month.
- Year-end: December 31 to January 1.
- Leap day: February 29 in a leap year; reject invalid February 29 in a non-leap year.
- Relative dates: today, tomorrow, day after tomorrow, next weekday.
- Weekday phrases must resolve to an actual future date in the tenant timezone.
- Reject past dates and past times today.
- Test booking horizon policy if a tenant configures a limit; do not assume 365 days is a hard booking limit.

## Timezone and persistence tests

- Tenant timezone differs from server timezone; caller-facing date/time remains tenant-local.
- Save local appointment as UTC and verify it renders as the same local date/time in the tenant calendar.
- Test timezone offset transitions where applicable; reject nonexistent local times and disambiguate repeated local times.
- Voice booking appears once in the existing appointment dashboard, with correct tenant, customer, service, staff, source and status.
- Availability and final create step both detect conflicts; two concurrent calls cannot reserve the same staff slot.
- Verify cancellation/reschedule and queue records remain aligned after date/time changes.

## Conversation behavior tests

- Caller gives date first, time later; preserve both.
- Caller gives time first, date later; preserve both.
- Caller says "today" after saying "5:30"; do not invent 5:30 AM.
- Caller corrects "9 AM — sorry, 9 PM"; use the latest explicit correction.
- Caller says "half past nine in the morning"; resolve to 09:30.
- Caller says "quarter to 8 PM"; resolve to 19:45 if supported, otherwise ask to clarify.
- Read back exact weekday, calendar date, time and AM/PM before confirmation.
- Do not create until the caller confirms the exact offered slot.
- If unavailable/outside hours, offer alternatives; never claim a booking was made unless the database write succeeded.

## Existing implementation review — issues to resolve before claiming PASS

- Current booking schedule stores weekday open/close times and has overnight-window handling in slot generation, but overnight early-morning lookup needs explicit cross-day tests.
- The former voice availability parser defaulted bare numeric 1–11 times to PM. The call-time-aware resolver must instead compare both interpretations against configured hours and call-start time, asking for clarification when both or neither qualify.
- Existing prompt says explicit AM should be preserved, and create-booking contains a correction heuristic. These heuristics must be tested together so availability and booking cannot interpret the same utterance differently.
- Current 24-hour seed maps 24-hour opening to 00:00–23:59. Verify final slot boundary and all-day semantics.
- Current weekday resolver and tenant timezone logic require tests across year/month/leap-day boundaries.

## Automated unit coverage

apps/api/tests/test_voice_booking_time.py covers UTC-to-tenant conversion, unique business-hours resolution, explicit AM preservation, ignoring assistant-suggested meridians, 24/7 clarification, neither-valid clarification, same-day past AM exclusion, and explicit 24-hour input.

## Release acceptance criteria

All cases above have automated tests where practical, plus end-to-end browser voice tests against an isolated test tenant. Attach test evidence and logs. Do not mark PASS from source inspection alone. Do not deploy or modify existing Render services as part of this test work.
