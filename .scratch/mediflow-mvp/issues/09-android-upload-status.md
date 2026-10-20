# 09: Build Android upload and persistent processing-status experience

Status: ready-for-agent
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

Not started. Record actual changes, verification commands/results, measured findings, and any remaining gate here. A readiness label does not imply completion or override the Blocked by line.

## Comments

- 2026-10-20: Created from the user-confirmed project plan. No implementation performed.
