# 10: Build laboratory results and authenticated PDF evidence navigation

Status: ready-for-agent
Type: task
Blocked by: 08, 09
Estimate: 8 hours
Target week: 5

## Outcome

A doctor can inspect each extracted field against the source document before reviewing it.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Select a PDF-viewer package only after checking its license, Android support, authenticated loading and page-navigation API.

## Scope

- Build structured laboratory row and summary views with missing/flagged/unresolved states and analysis provenance.
- Show supporting quotations and navigate to the exact source page using authenticated document loading.
- Use tabs on narrow Android screens and a split view when space permits; defer bounding-box highlighting.
- Clearly distinguish AI candidate data, clinician corrections and an approved snapshot; do not use confidence gauges or imply quote matching proves correctness.
- Handle token expiry, missing evidence, unreadable pages, reassignments and expired documents without leaking cached content.

## Acceptance criteria

- [ ] Every displayed extracted row opens its referenced source page or shows an explicit invalid/missing-evidence issue.
- [ ] PDF requests remain authorized on the backend; copied URLs cannot permanently expose the document.
- [ ] Viewers remain usable for multipage scanned and digital examples on a representative Android phone.
- [ ] Role/version labels prevent a patient-approved view from accidentally reusing the doctor draft payload.
- [ ] Logout, expiry and assignment loss clear/restrict the viewer appropriately.

## Verification

Manually inspect representative digital/scanned reports on Android and test page-reference bounds, authenticated loading, session expiry and assignment revocation.

## Implementation record

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
