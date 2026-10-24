# 10: Build laboratory results and authenticated PDF evidence navigation

Status: completed
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

- [x] Every displayed extracted row opens its referenced source page or shows an explicit invalid/missing-evidence issue.
- [x] PDF requests remain authorized on the backend; copied URLs cannot permanently expose the document.
- [x] Viewers remain usable for multipage scanned and digital examples on a representative Android phone.
- [x] Role/version labels prevent a patient-approved view from accidentally reusing the doctor draft payload.
- [x] Logout, expiry and assignment loss clear/restrict the viewer appropriately.

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

Final verification: Linux backend suite **168 passed, one optional Firebase-emulator
test skipped**; full Flutter suite **45 passed**; focused viewer **9 passed** after
review fixes. Python format/lint, mypy (39 sources), compileall, eight generated
contract artifacts, Flutter analysis/format, Dart contract smoke, nine hosting-probe
tests, two deployment-guard tests and the configured development APK build/install pass.

Android 15/API 35 verification used the normal installed APK, real synthetic Firebase
sign-in and a local test API with invented in-memory cases/results. Both referenced
pages of a mixed native/scanned report rendered and were visually inspected;
reassignment cleared the displayed result/quotation/image and no private temporary
PDF files remained. Real Firebase account checks returned patient-approved and
assigned-doctor-draft payloads only; cross-patient, unassigned-doctor, administrator,
explicit patient-draft and unauthenticated/copied-URL access were denied. Session
expiry, retention expiry, late downloads, missing/out-of-bounds evidence, unreadable
pages and long quotations are covered through the confirmed public test boundaries.

Separate Standards/Spec reviews found one minor duplicated-error-handler smell and
one P2 busy source-link issue. Both were fixed; a failing regression verified the
source links disable during a delayed authorization refresh and re-enable afterward.
Both final reviews report **0 unresolved findings**. See [review-10.md](../review-10.md).

The test API, emulator and container VM were stopped. No new cloud resources,
model calls or cloud clinical-payload writes were made. This is read-only viewer
acceptance, not the later hosted full review workflow or extraction-accuracy gate.
See the [viewer contract and limits](../../../docs/evidence-viewer.md) and
[sanitized Android evidence](../../../evaluation/reports/evidence-viewer-android.json).

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-25: Completed implementation, confirmed public-boundary TDD, Linux/Flutter
  suites, Android digital/scanned inspection, real Firebase access matrix, both
  corrective review axes and local verification-resource teardown. Committed on main.
