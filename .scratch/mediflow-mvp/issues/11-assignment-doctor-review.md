# 11: Implement administrator assignment and immutable version-specific doctor review

Status: completed
Type: task
Blocked by: 04, 10
Estimate: 12 hours
Target week: 5

## Outcome

An eligible assigned doctor can turn an AI candidate into an auditable approved or rejected review without silent overwrites.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

The review screen must not make clinical claims. Audit event creation is part of the same reliable transition, not a best-effort client request.

## Scope

- Implement paginated administrator workflow lists, active eligible doctor lists, assignment/reassignment and sanitized status diagnostics without clinical payloads.
- Implement doctor assigned-case list and begin-review/approve/correct-and-approve/reject actions against an explicit analysis version.
- Require every blocking issue to be corrected or explicitly acknowledged unresolved with a reason before approval. Preserve source links and the original AI values.
- Use transactional/version checks and idempotency for review decisions; append immutable review history and update the approved snapshot atomically.
- Recheck current assignment at review time. Reprocessing requires fresh approval and leaves the existing approved snapshot visible until replacement approval.
- Record server-controlled assignment/review/audit events with appropriate authorship and timestamps.

## Acceptance criteria

- [x] Administrator can assign/reassign but cannot open PDFs, AI drafts, clinical results or correction payloads.
- [x] Only the currently assigned active doctor can review/reprocess a case.
- [x] Approve, correct-and-approve, qualified unresolved approval and reject are distinguishable, attributed and preserved.
- [x] Duplicate review requests do not create duplicate decisions; stale version/assignment conflicts cannot overwrite a newer result.
- [x] Rejected/failed replacement analyses do not remove the patient's previous approved result.

## Verification

Run API integration and concurrency tests for review/assignment races, duplicate requests, unresolved flags, preserved originals and replacement approval; complete the corresponding Android flows.

## Implementation record

Implemented administrator case/eligible-doctor pagination, assignment/reassignment,
safe diagnostics, assigned-doctor discovery, begin-review, approval/correction/
qualification/rejection, immutable paginated history and Android navigation/forms.
Transitions recheck server account eligibility, assignment, hospital, expiry, latest
analysis and optimistic versions in the same Firestore transaction that appends the
decision/audit event and updates the approved snapshot. Idempotency replays retain
the exact original outcome; a different payload conflicts. Rejected/failed
replacement analyses preserve the prior approval. Corrections preserve original AI
rows, all source references and explicit unresolved qualifications.

The user confirmed HTTP, Flutter screen/API and real Firestore emulator test
boundaries, plus review baseline `8e7ebd3`. Public-boundary TDD verified assignment,
duplicate approval and races, source-grounded corrections, mixed corrected/unresolved
approval, eligibility/reassignment/expiry/version conflicts, preserved originals and
replacement snapshots. The final Linux suite passed **190 tests** with one optional
Firebase test skipped. A separate real Firestore emulator run passed **28 tests**.
The full Flutter suite passed **52 tests**; seven focused assignment/review screen
tests include exact-payload/key retries, multiple citations, resume during an old
request, access revocation and a chooser held open across the polling interval.

Checks: Python format/lint, mypy (42 sources), compileall, eight generated contract
artifacts, Flutter analysis/format, Dart contract smoke, nine hosting-probe tests,
two deployment-guard tests, and the final debug APK build/install pass. Commands
follow `docs/development.md`; the Linux suite runs `python -m pytest -c
backend/pyproject.toml backend/tests` in the existing isolated amd64 test container.
Real persistence uses Firebase `emulators:exec` with
`MEDIFLOW_UPLOAD_TEST_FIRESTORE=1` for `test_reviews.py` and `test_results.py`.

Android 15/API 35 acceptance uses the final installed APK, real synthetic Firebase
sign-in and a localhost API with invented in-memory case/result fixtures. Actual
administrator assignment/reassignment, assigned-doctor discovery, begin-review,
qualified approval, immutable history and rejection with a reason were exercised.
Correction submissions, rejection, uncertain retries and access/lifecycle conflicts
are also covered by the
public screen/API suites. This does not claim the later ticket-12 hosted full-journey
or ticket-14 extraction-accuracy gates. No new cloud resources, model calls or cloud
clinical-data writes were made. See [workflow documentation](../../../docs/assignment-review.md)
and [sanitized Android evidence](../../../evaluation/reports/assignment-review-android.json).

Independent parallel Standards and Spec reviews found one minor naming smell and
three P2 correction/citation/lifecycle issues. All were corrected and regressions
added; both final reviews report **0 unresolved findings**. A separate long-field
validation edge case now safely returns 422, and polling pauses during assignment
selection. See [review-11.md](../review-11.md). Implementation commits: `5f5f97f`
and `49baa1f`. The test API and app were stopped; ADB confirms no emulator devices,
Firebase emulators exited after successful verification, and Colima confirms the
test VM is stopped.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-25: Implemented ticket 11, completed confirmed-boundary TDD and both corrective review axes, and committed on the current branch.
