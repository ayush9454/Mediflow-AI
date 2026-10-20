# 12: Complete the three role journeys and approved patient results

Status: ready-for-agent
Type: task
Blocked by: 09, 11
Estimate: 8 hours
Target week: 6

## Outcome

Connect the implemented slices into a coherent demonstration without exposing unapproved data.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Keep original source/AI versus reviewed record distinctions visible without creating a broad hospital ERP interface.

## Scope

- Complete patient case/history lists, approved rows/summary, review attribution, explicit unresolved qualifications and safe rejected/failed/expired messages.
- Complete doctor pending/reviewed views for currently assigned cases and administrator pending/assigned workload metadata needed for manual assignment.
- Make result selection server controlled: before approval return no draft payload; after approval return the correct snapshot even while a replacement processes.
- Polish navigation, empty states, loading/error handling and in-app refresh across the role journeys. Defer push notifications and operations analytics.
- Provide deterministic synthetic seed/reset accounts and a repeatable sample journey without hardcoding successful results.

## Acceptance criteria

- [ ] Patient → administrator → doctor → patient workflow completes on the Android APK using actual hosted services.
- [ ] Patient sees no AI result before approval and sees only the approved snapshot afterwards.
- [ ] Unresolved qualifications, rejected replacement state and approved-version attribution remain understandable.
- [ ] Each role's list is paginated/scoped and contains only the authorized fields.
- [ ] No screen promises deferred features or exposes implementation/secrets to the product user.

## Verification

Run an end-to-end journey with two patients, two doctors and an administrator, including reassignment, rejection, correction, reprocessing and account switching.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
