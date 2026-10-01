# Error Registry

Central record of significant QA, regression, deployment, and reliability failures discovered during production hardening.

## Status legend

- **Resolved** — corrective change committed and covered by a relevant regression/verification path.
- **Transient / operational** — not a product defect; record retained for incident history and monitoring.
- **Reverted / superseded** — a change introduced a problem and was replaced by a safer implementation.

## Incident register

| ID | Date | Component | Exact failure | Root cause | Impact | Solution | Commit / run | Regression / verification | Status |
|---|---|---|---|---|---|---|---|---|---|
| ERR-001 | 2026-09 | Voice QA | Full regression treated legitimate unconfigured-tenant handoff as a failure | Test harness incorrectly required configured tenant facts even when the correct behavior was safe handoff | False-negative regression result | Changed the workflow to accept successful non-empty responses for unconfigured facts while retaining booking/language assertions | `b6cca51c5f2e50cc9b9449fc52442ab2bdff7c27` | Full voice regression run `36293597200` | **Resolved** |
| ERR-002 | 2026-09 | Scenario matrix | Missing WHY delayed-service and HOW refund scenarios; outside-hours emergency expected incorrectly | Scenario fixture coverage was incomplete | Reduced QA coverage for required intent families | Added explicit scenarios and correct `unknown_if_unverified` expectation | `aa2a64a7cc3e6ae7ddd0500a7f61a4641cd1c217` | Scenario/QA matrix | **Resolved** |
| ERR-003 | 2026-09 | Safety fixtures | `cannot_book` lacked explicit `do_not_invent_reason` assertion | Safety contract was not explicit in the fixture | Generic safety coverage exposed a missing guard | Added explicit no-invent-reason expectation | `9a2bbe9ca47f04add1ec2f4bb39141ae3c11f152` | Safety regression matrix | **Resolved** |
| ERR-004 | 2026-09 | Safety fixtures | Responsibility questions lacked explicit `do_not_invent_owner` guard | Ownership must come from tenant configuration, not model inference | Risk of fabricated responsibility/ownership | Added explicit no-invent-owner assertion | `c7ab50058d74f75cd26a5509526186ded8c6833b` | Safety regression matrix | **Resolved** |
| ERR-005 | 2026-09 | Booking safety | `Book me for 7.` could be interpreted without confirmed time context | Ambiguous numeric booking input was not explicitly guarded | Risk of booking the wrong time | Added `do_not_book_without_time_confirmation` expectation | `bbea5e51310e9c9aac8b07fa7e29b2c38c5aa4c6` | Booking safety regression | **Resolved** |
| ERR-006 | 2026-09 | API rate limiting | GitHub Actions multi-tenant QA received HTTP 429 responses | Shared client/NAT rate-limit bucket allowed one tenant/workload to consume another tenant's budget | Large QA matrices stopped before completion | Scoped rate-limit keys by tenant/business and route; retained rate-limit protection | `74b421cb8ff69088e4f48a6af81cec7abbda1468` | Multi-tenant regression rerun | **Resolved** |
| ERR-007 | 2026-09-27 | Render deployment | Production registration request timed out with `ReadTimeout` during deployment | QA hit the API while Render was redeploying; deployment race/availability window | Regression run failed before functional testing | Treat deployment availability separately from application assertions; subsequent deployment verification required | Run `36314270989` | Render deploy/health verification | **Transient / operational** |
| ERR-008 | 2026-09-27 | Render startup | `IndentationError: unexpected indent` in `apps/api/app/main.py` | Rate-limit comment/code block had literal escaped newline text, producing malformed Python indentation | Render build completed but application startup failed | Corrected the rate-limit block formatting and pushed the fix | `dc07da831798ef417f4d22f27a4db36c4bca1d13` | Python/import/startup + Render deployment verification | **Resolved** |
| ERR-009 | 2026-09-27 | Realtime LLM tools | Provider-unsafe/unimplemented tool declarations were introduced during an attempted extension | New tool declarations did not have complete handler support across providers | Risk of provider incompatibility | Removed the unimplemented declarations and kept provider-safe tools only | `39238a...` → `cb1f6e2275d41e36af096b755e47c08fd90e150c` | Realtime provider regression | **Reverted / superseded** |

## Required incident-record fields

Every new significant failure should record:

1. Error ID
2. Date/time
3. Component
4. Exact error/message
5. Root cause
6. Impact
7. Corrective solution
8. Commit or deployment/run reference
9. Regression test/workflow proving the fix
10. Current status
11. Whether the issue is product, test-harness, infrastructure, or transient

## Operating rule

A green test result must not erase a historical failure. Keep the incident entry and update its status after the corrective verification. For transient infrastructure failures, record the environmental cause separately from product defects so QA results remain interpretable.

## Known verification references

- Multi-tenant QA matrix: restaurant 74/0 at the last recorded successful stage; cafe 74/0; hotel had 67/7 before rate-limit isolation exposed the shared-bucket issue.
- Full voice regression: successful run `36293597200` after correcting the invalid failure assertion.
- Latest source correction: `dc07da831798ef417f4d22f27a4db36c4bca1d13`.

This registry is an engineering audit trail. It should be updated whenever a new failure is found, not only when a failure remains open.
