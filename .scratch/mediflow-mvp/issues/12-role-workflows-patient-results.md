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

- [x] Patient → administrator → doctor → patient workflow completes on the Android APK using actual hosted services.
- [x] Patient sees no AI result before approval and sees only the approved snapshot afterwards.
- [x] Unresolved qualifications, rejected replacement state and approved-version attribution remain understandable.
- [x] Each role's list is paginated/scoped and contains only the authorized fields.
- [x] No screen promises deferred features or exposes implementation/secrets to the product user.

## Verification

Run an end-to-end journey with two patients, two doctors and an administrator, including reassignment, rejection, correction, reprocessing and account switching.

## Implementation record

In progress. Dependencies 09 and 11 are completed. Implementation baseline:
`d4698cb263d5ae637051044e7e4c610bfd2312a6` on `main`. Reused the existing confirmed
HTTP, Flutter and Firebase integration boundaries from tickets 04, 09 and 11.

Implemented role-authorized case views with bounded pagination and view-bound
cursors; doctor pending/reviewed and administrator assignment filters; server-owned
approval metadata; patient approved-version/reviewer/qualification presentation;
safe replacement messages; automatic review-history refresh after successful
actions; trusted seed account reset; and a repeatable synthetic sample journey.
The hosted probe uses an isolated run prefix and removes review/approved payloads
alongside run-owned upload/processing data.

The full isolated Linux backend suite passes 196 tests (two opt-in Firebase tests
skipped there). All 55 Flutter tests and 42 actual Firebase Auth/Firestore emulator
integration tests pass. Python format/lint/compile, mypy on 42 sources, eight
generated contract artifacts, Flutter analysis/format, Dart contract/API smoke,
nine hosting-probe tests, two deployment-guard tests and the final debug APK
build/install pass. Commands follow `docs/development.md`; Linux tests ran in the
existing isolated amd64 test container, and Firebase checks used
`firebase emulators:exec` with `MEDIFLOW_UPLOAD_TEST_FIRESTORE=1` for the case,
result, review and real-token/rules suites.

The installed Android 15/API 35 APK exercised actual Firebase sign-in, hosted
HTTPS API, Firestore, private Blob/Queue, configured model, event worker and
scheduled reconciler with two patients, two doctors and an administrator.
Observed assignment/reassignment revoked the former doctor's case; both doctors
subsequently approved only their current assignments. Patient A's first approval
included a source-grounded citation expansion and an explicit missing-flag
qualification, without altering the printed value. Original AI data and that
correction remain in immutable review history. The patient retained approved
version 1 while replacement version 2 processed and after its rejection.

The final replacement encountered `temporarily_unavailable` and recovered through
the normal automatic retry, without direct record changes. Four jobs committed
four immutable analyses with attempt counts 1, 1, 1 and 2. After fresh approval,
patient A saw approved version 3 with new attribution; patient B saw their separate
version 1 approved by doctor A. Actual hosted assertions verify owner preapproval
409, draft/cross-patient/former-doctor/admin clinical denial, scoped list counts,
metadata-only list fields, no-store headers and account/view-bound cursors.

Independent Standards and Spec reviews and corrective re-reviews report **zero
unresolved findings**. Reviews caught a stale documentation invariant and shared
probe Docker configuration; both were corrected. The real Android run also exposed
post-decision refresh and polling layout gaps; public-boundary regressions verified
their fixes. Implementation commits: `14a3f10`, `f3f51f5` and `1376d97`. See the
[review](../review-12.md), [sample journey](../../../docs/sample-journey.md),
[repeatable hosted probe](../../../tools/journey_smoke/README.md) and
[sanitized Android evidence](../../../evaluation/reports/role-journeys-android.json).

The app left zero private temporary PDFs and filtered Flutter diagnostics were
empty. App/emulator, Firebase emulators and the local test VM are stopped. Run-owned
Firestore payloads and reservations are confirmed absent. Azure resource-group
deletion is still finishing its empty `ScheduledForDelete` environment; verify
absence before marking this ticket complete. The APK uses debug signing and needs
a new hosted API configuration after teardown; release signing and held-out
extraction accuracy remain separate gates.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
