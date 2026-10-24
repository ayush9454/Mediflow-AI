# 09: Build Android upload and persistent processing-status experience

Status: in-progress
Progress: implementation and verification complete; confirming temporary Azure teardown
Type: task
Blocked by: 05, 06
Estimate: 10 hours
Target week: 2–4

## Outcome

A patient can upload an accepted PDF, understand its state and recover the workflow after closing the app.

## Context

- [Agreed specification](../spec.md)
- [Roadmap and gates](../roadmap.md)
- [Decisions and external-source checks](../decisions.md)
- [Ticket index](../README.md#implementation-tickets)

Use mocked processing states only in explicit test configurations; the recorded final demonstration must exercise hosted processing.

## Scope

- Build synthetic-only acknowledgement, PDF selection, upload validation hints, progress, case list and status detail screens.
- Use server-created IDs, idempotency keys and bounded request retries so interrupted uploads/completion calls reuse the correct report.
- Display distinct uploading, processing, awaiting assignment/review, failed/rejected and expired messages from authoritative backend state.
- Poll only while relevant screens are active; refresh on resume and show cold-start, offline, session-expired and quota messages.
- Do not display AI drafts or cache protected clinical content across account changes. Provide safe access to the patient's original report.

## Acceptance criteria

- [ ] Installable development APK uploads a valid PDF through the hosted API and shows its durable case/job state.
- [ ] App close/reopen restores the same case and current server status without duplicating uploads or stopping backend work.
- [ ] File limits, upload interruption, expired session, cold start and quota failures have actionable messages.
- [ ] Screen transitions distinguish a document rejection from doctor rejection and avoid presenting workflow state as medical urgency.
- [ ] No public storage URL, AI key, internal error payload or draft analysis appears in the patient UI.

## Verification

Run on an Android emulator/device, including process kill/reopen, network interruption, another account login and hosted cold start. Automate state/retry behavior where it catches real regressions.

## Implementation record

Implemented the patient Reports/History tabs, Android system PDF picker, bounded upload streaming/progress, private owner-scoped recovery journal, stable operation keys, canonical duplicate recovery, paginated patient cases and authoritative status detail. Original PDFs are fetched through authenticated backend bytes and rendered with bounded private temporary files; source/images are cleared on background, disposal and account/hospital changes. No draft/result endpoint is used.

All three testing interfaces were confirmed by the user on 2026-10-24: upload/API/recovery, patient screens/lifecycle, and backend cases/document HTTP. Tests cover lost registration/completion, retired duplicate aliases, quota/session messages, offline resume, protected original response validation, foreground polling, late picker/download responses and hospital-scope replacement.

Real hosted acceptance uses the normal API/event worker/reconciler with Firebase/Firestore, private Blob/queue and the real configured provider. The installed Android 15/API 35 development APK uploaded an invented PDF, recovered after offline interruption, and reopened the canonical case after process death. Processing continued independently from queued through processing to succeeded, with one job attempt and one immutable analysis. Repeated exact-PDF completion kept one case/job. The original PDF rendered through authenticated access. A second patient login showed no first-patient reports.

Cold-start acceptance observed zero API replicas before launching the final APK. The first health check showed the safe unavailable/starting message; the displayed retry succeeded, followed by sign-in and the same completed case. All run-owned Firestore payloads/reservations are verified absent. Azure group deletion remains in progress; this ticket stays in progress until its absence is confirmed. See [patient upload behavior](../../../docs/patient-upload.md), [reproducible hosted probe](../../../tools/patient_smoke/README.md), and [review](../review-09.md).

Validation: 162 backend tests passed in Linux (one optional Firebase-emulator test skipped), 33 Flutter tests passed; Python format/lint, mypy on 38 source files, 8 generated contract artifacts, Flutter analysis, Dart contract/API smoke and the configured APK build/install passed. Separate Standards/Spec reviews found account/lifecycle cleanup gaps; failing regression tests verified the fixes. Both final corrective reviews found no unresolved findings.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-24: User invoked implement for this ticket. Repository and hosted-service
  prerequisites inspected; existing Android emulator/toolchain prepared. The
  prior confirmation concerned ticket 08's laboratory/provider/worker interfaces;
  ticket 09's proposed Android/case-list testing areas were subsequently confirmed.
