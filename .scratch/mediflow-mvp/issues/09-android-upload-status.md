# 09: Build Android upload and persistent processing-status experience

Status: in-progress
Progress: all three test interfaces confirmed; implementation active
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

Investigation started against baseline `67f6615`. Tickets 05 and 06 are complete.
The upload, completion, report metadata and private original-document endpoints
already exist. `GET /cases` remains a placeholder and needs a patient-scoped,
paginated implementation for recovery after app restart. Android currently has
authentication and role shells, with no upload workflow.

Planned implementation uses the Android system PDF picker, bounded in-memory PDF
bytes, an account-scoped recovery journal containing only the metadata and
idempotency keys needed to resume an interrupted upload, authoritative server
case/status refresh, foreground-only polling, and authenticated original-PDF
access. PDF bytes, tokens and AI drafts must not be persisted in the journal.

Proposed testing interfaces: (1) Android upload/API/recovery workflow for retries,
restart and account changes; (2) patient screens/lifecycle for status messages and
polling; (3) backend case-list/document HTTP APIs for pagination and permissions.
The TDD skill requires explicit confirmation before tests at new interfaces.
The user confirmed all three areas on 2026-10-24. Implementation and real Android/
hosted API acceptance are now in progress.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.

- 2026-10-24: User invoked implement for this ticket. Repository and hosted-service
  prerequisites inspected; existing Android emulator/toolchain prepared. The
  prior confirmation concerned ticket 08's laboratory/provider/worker interfaces;
  ticket 09's proposed Android/case-list testing areas await confirmation.
