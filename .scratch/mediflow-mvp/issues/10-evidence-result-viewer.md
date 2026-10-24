# 10: Build laboratory results and authenticated PDF evidence navigation

Status: in-progress
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

Implemented the role-scoped result HTTP reader, immutable approved-snapshot read
contract, client result-kind/identity checks, laboratory rows/summary/provenance,
explicit evidence issues, narrow tabs/wide split view, authenticated exact-page
navigation and lifecycle/retention/access-revocation clearing. The user confirmed
all three testing boundaries and starting review commit `4b59cca` on 2026-10-25.
Assignment, assigned-case discovery and review writes remain in ticket 11; doctors
can currently open an assigned report by its server-created reference.

Verification so far: Linux backend suite **168 passed, one optional Firebase-emulator
test skipped**; full Flutter suite **44 passed**; focused viewer **8 passed** after
format-only fixes. Python format/lint, mypy (39 sources), compileall, eight generated
contract artifacts, Flutter analysis, Dart contract smoke, nine hosting-probe tests,
two deployment-guard tests and the configured development APK build pass.
A real Firebase doctor sign-in against the local synthetic test API opened and
rendered a native source page on Android 15/API 35. Reassignment cleared the viewer;
private temporary PDF files were absent. Final scanned-page inspection and the
required separate Standards/Spec review are in progress. See the
[viewer contract and limits](../../../docs/evidence-viewer.md).

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
